import time
import youtube_handler
from obs_handler import OBSHandler
from datetime import datetime, timedelta
import yaml
import os
from logger import logger, setup_logging # ロギング設定をインポート

settings = {}

def load_config():
    global settings
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            settings.update(yaml.safe_load(f))
        # config.yaml読み込み後にロガーをセットアップ
        setup_logging(settings)
        logger.info("config.yamlを読み込みました。")
    except FileNotFoundError:
        logger.error(f"エラー: config.yamlが見つかりません。パス: {config_path}")
        exit(1)
    except yaml.YAMLError as e:
        logger.error(f"エラー: config.yamlの解析中にエラーが発生しました: {e}")
        exit(1)

def main():
    load_config()
    logger.info("--- YouTubeライブ配信自動化スクリプトを開始します ---")

    # 1. YouTube APIの認証
    logger.info("YouTube APIへの認証を試みます...")
    youtube = youtube_handler.get_authenticated_service(settings)
    if not youtube:
        logger.error("エラー: YouTube APIの認証に失敗しました。スクリプトを終了します。")
        return
    logger.info("YouTube API認証に成功しました。")

    loop_count = settings['loop']['count']
    loop_duration_hours = settings['loop']['duration_hours']
    expiration_datetime_str = settings['loop']['expiration_datetime']

    expiration_datetime = None
    if expiration_datetime_str:
        try:
            expiration_datetime = datetime.strptime(expiration_datetime_str, "%Y%m%dT%H%M%S")
        except ValueError:
            logger.warning(f"警告: config.yamlのexpiration_datetimeの形式が不正です: {expiration_datetime_str}。デフォルト値を使用します。")
            expiration_datetime = datetime.strptime("20991231T235959", "%Y%m%dT%H%M%S")
    else:
        expiration_datetime = datetime.strptime("20991231T235959", "%Y%m%dT%H%M%S")

    # If all are 0, it's an infinite loop
    if loop_count == 0 and loop_duration_hours == 0 and expiration_datetime == datetime.strptime("20991231T235959", "%Y%m%dT%H%M%S"):
        logger.info("全てのループ設定が0のため、無限ループモードで実行します。")
        loop_count = 0 # 0 for infinite count
        loop_duration_hours = 0 # 0 for infinite duration
        expiration_datetime = None # None for no expiration

    start_time = time.time()
    loop_iteration = 0

    while True:
        current_time = time.time()
        current_datetime = datetime.now()

        # Check termination conditions
        if loop_count != 0 and loop_iteration >= loop_count:
            logger.info(f"設定されたループ回数 ({loop_count}) に達しました。スクリプトを終了します。")
            break
        if loop_duration_hours != 0 and (current_time - start_time) / 3600 >= loop_duration_hours:
            logger.info(f"設定された合計配信時間 ({loop_duration_hours}時間) に達しました。スクリプトを終了します。")
            break
        if expiration_datetime is not None and current_datetime >= expiration_datetime:
            logger.info(f"設定された有効期限 ({expiration_datetime.strftime('%Y-%m-%d %H:%M:%S')}) に達しました。スクリプトを終了します。")
            break

        logger.info(f"--- ループ {loop_iteration + 1} を開始します ---")

        # 2. OBSハンドラの初期化 (各ループの開始時に再接続)
        logger.info("OBSハンドラを初期化します...")
        obs_handler = OBSHandler(settings)
        if not obs_handler.client:
            logger.error("エラー: OBSへの接続に失敗しました。スクリプトを終了します。")
            return
        logger.info("OBSハンドラの初期化に成功しました。")

        try:
            # 3. YouTubeに新しいライブ配信枠を作成し、ストリームキーを取得
            logger.info("YouTubeに新しいライブ配信枠を作成します...")
            stream_key = youtube_handler.create_youtube_broadcast(youtube, settings)
            if not stream_key:
                logger.error("エラー: ライブ配信枠の作成に失敗しました。次のループを試行します。")
                time.sleep(60) # Wait for a minute before retrying
                continue
            logger.info(f"ライブ配信枠の作成に成功しました。ストリームキー: {stream_key}")

            # 4. OBSにストリームキーを設定
            logger.info("OBSにストリームキーを設定します...")
            if not obs_handler.set_stream_settings(stream_key):
                logger.error("エラー: OBSストリームキーの設定に失敗しました。スクリプトを終了します。")
                return # スクリプトを終了

            # 5. OBSで配信を開始
            logger.info("OBSで配信を開始します...")
            obs_handler.start_stream()

            # 6. OBSが実際に配信を開始するまで待機
            if obs_handler.wait_for_stream_to_start(timeout=settings['script']['obs_stream_start_timeout_seconds']):
                logger.info("OBSが配信を開始しました。")
                def format_duration(seconds):
                    hours = int(seconds // 3600)
                    minutes = int((seconds % 3600) // 60)
                    seconds = int(seconds % 60)
                    parts = []
                    if hours > 0:
                        parts.append(f"{hours}時間")
                    if minutes > 0:
                        parts.append(f"{minutes}分")
                    if seconds > 0 or not parts: # Include seconds if it's the only unit or if all are zero
                        parts.append(f"{seconds}秒")
                    return "".join(parts)

                formatted_duration = format_duration(settings['script']['stream_actual_duration_seconds'])
                logger.info(f"{formatted_duration}配信を継続します。")
                time.sleep(settings['script']['stream_actual_duration_seconds'])

                # 7. 配信を停止
                logger.info("配信を停止します...")
                obs_handler.stop_stream()
                logger.info("配信停止コマンドを送信しました。")
            else:
                logger.warning("警告: OBSが指定時間内に配信を開始しませんでした。次のループを試行します。")
                time.sleep(60) # Wait for a minute before retrying
                continue

        except Exception as e:
            logger.error(f"スクリプト実行中に予期せぬエラーが発生しました: {e}")
            logger.info("次のループを試行します。")
            time.sleep(60) # Wait for a minute before retrying
        finally:
            # OBSとの接続は各ループの開始時に再確立されるため、ここでは切断しない
            logger.info("--- ループ終了処理完了 ---")
            time.sleep(10) # Small delay before starting the next loop iteration

        loop_iteration += 1

    logger.info("--- スクリプトを終了します ---")

if __name__ == '__main__':
    main()