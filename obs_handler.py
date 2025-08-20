import obsws_python as obs
import subprocess
import time
import yaml
import os
from logger import logger # ロガーをインポート

class OBSHandler:
    def __init__(self, settings):
        self.settings = settings
        try:
            # 接続試行（タイムアウトを3秒に設定）
            self.client = obs.ReqClient(
                host=self.settings['obs']['host'],
                port=self.settings['obs']['port'],
                password=self.settings['obs']['password'],
                timeout=self.settings['obs_execution']['connection_timeout_seconds']
            )
            logger.info("OBSに接続しました。")
        except ConnectionRefusedError:
            logger.warning("OBSに接続できませんでした。OBSを起動します...")
            try:
                # macOSのパスからOBSを起動
                subprocess.Popen(['open', self.settings['obs']['app_path']])
                logger.info("OBSの起動を10秒間待機します...")
                time.sleep(self.settings['obs_execution']['launch_wait_seconds'])
                # 再度接続を試行
                self.client = obs.ReqClient(
                    host=self.settings['obs']['host'],
                    port=self.settings['obs']['port'],
                    password=self.settings['obs']['password']
                )
                logger.info("OBSに再接続しました。")
            except Exception as e:
                logger.error(f"OBSの起動または再接続中にエラーが発生しました: {e}")
                self.client = None # 接続失敗
        except Exception as e:
            logger.error(f"OBSへの接続中に予期せぬエラーが発生しました: {e}")
            self.client = None # 接続失敗

    def set_stream_settings(self, stream_key):
        if not self.client:
            logger.error("OBSクライアントが初期化されていないため、配信設定を変更できません。")
            return False

        for attempt in range(self.settings['obs_execution']['set_stream_settings_max_retries']):
            try:
                logger.info(f"OBSにストリーム設定をセットします... (試行 {attempt + 1}/{self.settings['obs_execution']['set_stream_settings_max_retries']}, キー: ...{stream_key[-4:]})")
                self.client.set_stream_service_settings(
                    ss_type='rtmp_custom',
                    ss_settings={
                        'server': self.settings['youtube']['rtmp_url'],
                        'key': stream_key,
                        'service': 'YouTube / YouTube Gaming'
                    }
                )
                logger.info("OBSのストリーム設定を更新しました。")
                return True # 成功したらループを抜ける
            except Exception as e:
                logger.error(f"OBSのストリーム設定中にエラーが発生しました: {e}")
                if attempt < self.settings['obs_execution']['set_stream_settings_max_retries'] - 1:
                    logger.warning(f"リトライします... ({self.settings['obs_execution']['set_stream_settings_retry_delay_seconds']}秒後)")
                    time.sleep(self.settings['obs_execution']['set_stream_settings_retry_delay_seconds'])
                else:
                    logger.error("最大リトライ回数に達しました。ストリーム設定に失敗しました。")
                    return False # 最大リトライ回数に達しても成功しなかった場合

    def start_stream(self):
        if not self.client:
            logger.error("OBSクライアントが初期化されていないため、配信を開始できません。")
            return
        self.client.start_stream()
        logger.info("OBS: 配信を開始しました。")
        # エラーハンドリングを追加
        # except Exception as e:
        #     logger.error(f"OBS配信の開始中にエラーが発生しました: {e}")

    def stop_stream(self):
        if not self.client:
            logger.error("OBSクライアントが初期化されていないため、配信を停止できません。")
            return
        self.client.stop_stream()
        logger.info("OBS: 配信を停止しました。")
        # エラーハンドリングを追加
        # except Exception as e:
        #     logger.error(f"OBS配信の停止中にエラーが発生しました: {e}")

    def disconnect(self):
        if self.client:
            self.client.disconnect()
            logger.info("OBS: 接続を解除しました。")

    def wait_for_stream_to_start(self, timeout=30):
        if not self.client:
            logger.error("OBSクライアントが初期化されていないため、ストリーム開始を待機できません。")
            return
        logger.info(f"OBSがストリームを開始するのを最大{timeout}秒間待機します...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                status = self.client.get_stream_status()
                if status.output_active:
                    logger.info("OBSがストリームを開始しました。")
                    return True
            except Exception as e:
                logger.error(f"ストリームステータスの取得中にエラーが発生しました: {e}")
            time.sleep(self.settings['obs_execution']['stream_status_polling_interval_seconds'])
        logger.warning(f"警告: {timeout}秒以内にOBSがストリームを開始しませんでした。")
        return False
