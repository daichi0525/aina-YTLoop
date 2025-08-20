import time
import youtube_handler
from obs_handler import OBSHandler
from datetime import datetime, timedelta
import yaml
import os
from logger import logger, setup_logging

settings = {}

def load_config():
    """
    設定ファイル (config.yaml) を読み込み、ロギングを設定します。
    """
    global settings
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            settings.update(yaml.safe_load(f))
        setup_logging(settings) # ロガーをconfig.yamlの設定で初期化
        logger.info("設定ファイルを正常に読み込みました。")
    except FileNotFoundError:
        logger.critical(f"設定ファイルが見つかりません: {config_path}。スクリプトを終了します。")
        exit(1)
    except yaml.YAMLError as e:
        logger.critical(f"設定ファイルの解析中にエラーが発生しました: {e}。スクリプトを終了します。")
        exit(1)

def main():
    """
    メイン処理を実行します。
    YouTubeライブ配信の自動化フローを管理します。
    """
    load_config()
    logger.info("YouTubeライブ自動化スクリプトを開始します。")

    # 1. YouTube API認証
    logger.info("YouTube API認証を試行中...")
    youtube = youtube_handler.get_authenticated_service(settings)
    if not youtube:
        logger.critical("YouTube API認証に失敗しました。スクリプトを終了します。")
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
            logger.warning(f"config.yamlのexpiration_datetime形式が不正です: '{expiration_datetime_str}'。デフォルト値 (2099-12-31 23:59:59) を使用します。")
            expiration_datetime = datetime.strptime("20991231T235959", "%Y%m%dT%H%M%S")
    else:
        expiration_datetime = datetime.strptime("20991231T235959", "%Y%m%dT%H%M%S")

    # 全てのループ設定が0の場合、無限ループモードで実行
    if loop_count == 0 and loop_duration_hours == 0 and expiration_datetime == datetime.strptime("20991231T235959", "%Y%m%dT%H%M%S"):
        logger.info("ループ設定が全て無制限のため、無限ループモードで実行します。")
        loop_count = 0
        loop_duration_hours = 0
        expiration_datetime = None

    start_time = time.time()
    loop_iteration = 0

    while True:
        current_time = time.time()
        current_datetime = datetime.now()

        # 終了条件の確認
        if loop_count != 0 and loop_iteration >= loop_count:
            logger.info(f"終了条件: ループ回数 ({loop_count}) に達しました。スクリプトを終了します。")
            break
        if loop_duration_hours != 0 and (current_time - start_time) / 3600 >= loop_duration_hours:
            logger.info(f"終了条件: 合計配信時間 ({loop_duration_hours}時間) に達しました。スクリプトを終了します。")
            break
        if expiration_datetime is not None and current_datetime >= expiration_datetime:
            logger.info(f"終了条件: 有効期限 ({expiration_datetime.strftime('%Y-%m-%d %H:%M:%S')}) に達しました。スクリプトを終了します。")
            break

        logger.info(f"ループ {loop_iteration + 1} / {loop_count if loop_count != 0 else '無限'} を開始します。")

        # 2. OBSハンドラの初期化 (各ループの開始時に再接続)
        logger.info("OBSハンドラの初期化と接続を試行中...")
        obs_handler = OBSHandler(settings)
        if not obs_handler.client:
            logger.error("OBSへの接続に失敗しました。スクリプトを終了します。")
            return
        logger.info("OBSハンドラの初期化と接続に成功しました。")

        try:
            # 3. YouTubeに新しいライブ配信枠を作成し、ストリームキーを取得
            logger.info("新しいYouTubeライブ配信枠を作成中...")
            stream_key = youtube_handler.create_youtube_broadcast(youtube, settings)
            if not stream_key:
                logger.error("ライブ配信枠の作成に失敗しました。次のループを試行します。")
                time.sleep(60)
                continue
            logger.info(f"ライブ配信枠の作成に成功しました。ストリームキー: {stream_key}")

            # 4. OBSにストリームキーを設定
            logger.info("OBSにストリームキーを設定中...")
            if not obs_handler.set_stream_settings(stream_key):
                logger.error("OBSストリームキーの設定に失敗しました。スクリプトを終了します。")
                return

            # 5. OBSで配信を開始
            logger.info("OBSに配信開始コマンドを送信中...")
            obs_handler.start_stream()

            # 6. OBSが実際に配信を開始するまで待機
            if obs_handler.wait_for_stream_to_start(timeout=settings['script']['obs_stream_start_timeout_seconds']):
                logger.info("OBSが正常に配信を開始しました。")
                def format_duration(seconds):
                    """秒数を時間、分、秒の形式にフォーマットします。"""
                    hours = int(seconds // 3600)
                    minutes = int((seconds % 3600) // 60)
                    seconds = int(seconds % 60)
                    parts = []
                    if hours > 0:
                        parts.append(f"{hours}時間")
                    if minutes > 0:
                        parts.append(f"{minutes}分")
                    if seconds > 0 or not parts: # 秒が唯一の単位の場合、または全てがゼロの場合に秒を含める
                        parts.append(f"{seconds}秒")
                    return "".join(parts)

                formatted_duration = format_duration(settings['script']['stream_actual_duration_seconds'])
                logger.info(f"設定された配信時間 ({formatted_duration}) 配信を継続します。")
                time.sleep(settings['script']['stream_actual_duration_seconds'])

                # 7. 配信を停止
                logger.info("OBSに配信停止コマンドを送信中...")
                obs_handler.stop_stream()
                logger.info("OBS: 配信停止コマンドを正常に送信しました。")
            else:
                logger.warning("OBSが指定時間内に配信を開始しませんでした。次のループを試行します。")
                time.sleep(60)
                continue

        except Exception as e:
            logger.error(f"スクリプト実行中に予期せぬエラーが発生しました: {e}", exc_info=True) # exc_info=Trueでスタックトレースを出力
            logger.info("次のループを試行します。")
            time.sleep(60)
        finally:
            logger.info("ループ処理が完了しました。")
            time.sleep(10)

        loop_iteration += 1

    logger.info("スクリプトを終了します。")

if __name__ == '__main__':
    main()
