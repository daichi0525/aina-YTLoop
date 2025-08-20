import time
import youtube_handler
from obs_handler import OBSHandler
from datetime import datetime
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
        setup_logging(settings)
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

    # 2. OBSハンドラの初期化と接続
    obs_handler = OBSHandler(settings)
    if not obs_handler.connect():
        logger.critical("OBSへの初回接続に失敗しました。スクリプトを終了します。")
        return

    loop_count = settings['loop']['count']
    loop_duration_hours = settings['loop']['duration_hours']
    expiration_datetime_str = settings['loop']['expiration_datetime']

    expiration_datetime = None
    if expiration_datetime_str:
        try:
            expiration_datetime = datetime.strptime(expiration_datetime_str, "%Y%m%dT%H%M%S")
        except ValueError:
            logger.warning(f"config.yamlのexpiration_datetime形式が不正です: '{expiration_datetime_str}'。デフォルト値 (2099-12-31 23:59:59) を使用します。")
            expiration_datetime = datetime.max
    else:
        expiration_datetime = datetime.max

    start_time = time.time()
    loop_iteration = 0
    last_source_reload_time = time.time()

    try:
        while True:
            current_time = time.time()
            current_datetime = datetime.now()

            # 終了条件の確認
            if loop_count != 0 and loop_iteration >= loop_count:
                logger.info(f"終了条件: ループ回数 ({loop_count}) に達しました。")
                break
            if loop_duration_hours != 0 and (current_time - start_time) / 3600 >= loop_duration_hours:
                logger.info(f"終了条件: 合計配信時間 ({loop_duration_hours}時間) に達しました。")
                break
            if expiration_datetime != datetime.max and current_datetime >= expiration_datetime:
                logger.info(f"終了条件: 有効期限 ({expiration_datetime.strftime('%Y-%m-%d %H:%M:%S')}) に達しました。")
                break

            logger.info(f"ループ {loop_iteration + 1} / {loop_count if loop_count != 0 else '無限'} を開始します。")

            try:
                # 3. YouTubeに新しいライブ配信枠を作成し、ストリームキーを取得
                logger.info("新しいYouTubeライブ配信枠を作成中...")
                stream_key = youtube_handler.create_youtube_broadcast(youtube, settings)
                if not stream_key:
                    logger.error("ライブ配信枠の作成に失敗しました。60秒後に次のループを試行します。")
                    time.sleep(60)
                    continue
                logger.info(f"ライブ配信枠の作成に成功しました。ストリームキー: ...{stream_key[-4:]}")

                # 4. OBSにストリームキーを設定
                logger.info("OBSにストリームキーを設定中...")
                if not obs_handler.set_stream_settings(stream_key):
                    logger.error("OBSストリームキーの設定に失敗しました。次のループを試行します。")
                    time.sleep(60)
                    continue

                # 5. OBSで配信を開始
                logger.info("OBSに配信開始コマンドを送信中...")
                obs_handler.start_stream()

                # 6. OBSが実際に配信を開始するまで待機
                if obs_handler.wait_for_stream_to_start(timeout=settings['script']['obs_stream_start_timeout_seconds']):
                    logger.info("OBSが正常に配信を開始しました。")
                    
                    def format_duration(seconds):
                        h = int(seconds // 3600)
                        m = int((seconds % 3600) // 60)
                        s = int(seconds % 60)
                        return f"{h}時間{m}分{s}秒"

                    duration_str = format_duration(settings['script']['stream_actual_duration_seconds'])
                    logger.info(f"設定された配信時間 ({duration_str}) 配信を継続します。")

                    # 配信中の定期処理
                    stream_start_time = time.time()
                    while (time.time() - stream_start_time) < settings['script']['stream_actual_duration_seconds']:
                        if settings['obs_execution'].get('enable_source_reload', False):
                            reload_interval = settings['obs_execution'].get('source_reload_interval_seconds', 300)
                            if (time.time() - last_source_reload_time) >= reload_interval:
                                logger.info(f"ソースの定期的な再読み込みを実行中 ({reload_interval}秒ごと)...")
                                for source_name in settings['obs_execution'].get('source_names', []):
                                    obs_handler.reload_source(source_name)
                                last_source_reload_time = time.time()
                        
                        time.sleep(settings['obs_execution']['stream_status_polling_interval_seconds'])

                    logger.info("OBSに配信停止コマンドを送信中...")
                    obs_handler.stop_stream()
                    logger.info("OBS配信停止コマンドを正常に送信しました。")
                else:
                    logger.warning("OBSが指定時間内に配信を開始しませんでした。次のループを試行します。")
                    time.sleep(60)
                    continue

            except Exception as e:
                logger.error(f"ループ内処理で予期せぬエラーが発生しました: {e}", exc_info=True)
                logger.info("60秒後に次のループを試行します。")
                time.sleep(60)
            
            logger.info("ループ処理が完了しました。10秒後に次の処理へ進みます。")
            time.sleep(10)
            loop_iteration += 1

    except KeyboardInterrupt:
        logger.info("ユーザーによってスクリプトが中断されました。")
    finally:
        logger.info("クリーンアップ処理を実行します。")
        obs_handler.disconnect()
        logger.info("スクリプトを終了します。")

if __name__ == '__main__':
    main()
