import obsws_python as obs
import subprocess
import time
from functools import wraps
from logger import logger

def ensure_connection(func):
    """
    OBS接続を保証するためのデコレータ。
    接続がない場合は接続を試み、リクエストに失敗した場合は再接続を試みます。
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.client:
            logger.warning("OBSクライアントが未接続です。自動的に接続を試みます。")
            if not self.connect():
                logger.error(f"OBSへの接続に失敗したため、'{func.__name__}' を実行できません。")
                return None # 接続失敗時はNoneを返す

        try:
            return func(self, *args, **kwargs)
        except (ConnectionRefusedError, BrokenPipeError) as e:
            logger.warning(f"OBSリクエスト中に接続エラーが発生しました ({type(e).__name__})。再接続を試みます...")
            self.disconnect() # 古い接続を閉じる
            if self.connect():
                logger.info("OBSへの再接続に成功しました。リクエストを再試行します。")
                try:
                    return func(self, *args, **kwargs) # 再度実行
                except Exception as e_retry:
                    logger.error(f"再試行後も '{func.__name__}' の実行に失敗しました: {e_retry}", exc_info=True)
                    return None
            else:
                logger.error(f"OBSへの再接続に失敗しました。'{func.__name__}' を実行できません。")
                return None
        except Exception as e:
            logger.error(f"'{func.__name__}' の実行中に予期せぬエラーが発生しました: {e}", exc_info=True)
            return None
    return wrapper

class OBSHandler:
    """
    OBS Studioとの連携を管理するクラス。
    OBS WebSocketプロトコルを使用してOBSを制御します。
    """
    def __init__(self, settings):
        """
        OBSHandlerのコンストラクタ。
        OBS接続設定を保存し、クライアントを初期化します。
        """
        self.settings = settings
        self.client = None

    def connect(self):
        """
        OBS WebSocketに接続し、クライアントを初期化します。
        接続に失敗した場合はFalseを返します。
        """
        if self.client:
            logger.debug("OBSクライアントは既に接続されています。")
            return True

        try:
            logger.debug("OBSへの接続を試行中...")
            self.client = obs.ReqClient(
                host=self.settings['obs']['host'],
                port=self.settings['obs']['port'],
                password=self.settings['obs']['password'],
                timeout=self.settings['obs_execution']['connection_timeout_seconds']
            )
            logger.info("OBSに正常に接続しました。")
            return True
        except ConnectionRefusedError:
            logger.warning("OBSに接続できませんでした。OBSを起動して再接続を試行します...")
            try:
                subprocess.Popen(['open', self.settings['obs']['app_path']])
                logger.info(f"OBSの起動を{self.settings['obs_execution']['launch_wait_seconds']}秒間待機します。")
                time.sleep(self.settings['obs_execution']['launch_wait_seconds'])
                self.client = obs.ReqClient(
                    host=self.settings['obs']['host'],
                    port=self.settings['obs']['port'],
                    password=self.settings['obs']['password'],
                    timeout=self.settings['obs_execution']['connection_timeout_seconds']
                )
                logger.info("OBSに再接続しました。")
                return True
            except Exception as e:
                logger.error(f"OBSの起動または再接続中にエラーが発生しました: {e}", exc_info=True)
                self.client = None
                return False
        except Exception as e:
            logger.error(f"OBSへの接続中に予期せぬエラーが発生しました: {e}", exc_info=True)
            self.client = None
            return False

    def disconnect(self):
        """
        OBSとの接続を解除します。
        """
        if self.client:
            try:
                self.client.disconnect()
                logger.info("OBSとの接続を解除しました。")
            except Exception as e:
                logger.error(f"OBS接続の解除中にエラーが発生しました: {e}", exc_info=True)
            finally:
                self.client = None

    @ensure_connection
    def set_stream_settings(self, stream_key):
        """
        OBSのストリーム設定（RTMPサーバーとストリームキー）を設定します。
        もしOBSが配信中の場合、安全のために既存の配信を停止してから設定を試みます。
        """
        try:
            # 現在のストリーム状態を確認
            status = self.client.get_stream_status()
            if status and status.output_active:
                logger.warning("OBSは現在配信中です。前回のストリームが残っている可能性があるため、強制的に停止します。")
                self.stop_stream()
                
                # 配信が停止するのを待機 (タイムアウト付き)
                stop_wait_start_time = time.time()
                while time.time() - stop_wait_start_time < 30: # 最大30秒待機
                    status = self.client.get_stream_status()
                    if not (status and status.output_active):
                        logger.info("残っていたOBSストリームを正常に停止しました。")
                        break
                    time.sleep(1)
                else:
                    logger.error("残っていたストリームの停止に失敗しました。設定を続行できません。")
                    return False

        except Exception as e:
            logger.error(f"ストリーム状態の確認中にエラーが発生しました: {e}", exc_info=True)
            return False

        # ストリーム設定の適用（リトライ処理込み）
        for attempt in range(self.settings['obs_execution']['set_stream_settings_max_retries']):
            try:
                logger.debug(f"OBSにストリーム設定をセット中... (試行 {attempt + 1}/{self.settings['obs_execution']['set_stream_settings_max_retries']}, キー: ...{stream_key[-4:]})")
                self.client.set_stream_service_settings(
                    ss_type='rtmp_custom',
                    ss_settings={
                        'server': self.settings['youtube']['rtmp_url'],
                        'key': stream_key,
                        'service': 'YouTube / YouTube Gaming'
                    }
                )
                logger.info("OBSのストリーム設定を正常に更新しました。")
                return True
            except Exception as e:
                # 配信中に設定しようとした場合のエラーをここで捕捉してリトライ
                logger.error(f"OBSのストリーム設定中にエラーが発生しました: {e}", exc_info=True)
                if attempt < self.settings['obs_execution']['set_stream_settings_max_retries'] - 1:
                    logger.warning(f"ストリーム設定のリトライを行います ({self.settings['obs_execution']['set_stream_settings_retry_delay_seconds']}秒後)。")
                    time.sleep(self.settings['obs_execution']['set_stream_settings_retry_delay_seconds'])
                else:
                    logger.critical("ストリーム設定の最大リトライ回数に達しました。設定に失敗しました。")
                    return False
        return False

    @ensure_connection
    def start_stream(self):
        """
        OBSで配信を開始します。
        """
        self.client.start_stream()
        logger.info("OBS: 配信開始コマンドを送信しました。")

    @ensure_connection
    def stop_stream(self):
        """
        OBSで配信を停止します。
        """
        self.client.stop_stream()
        logger.info("OBS: 配信停止コマンドを送信しました。")

    @ensure_connection
    def wait_for_stream_to_start(self, timeout=30):
        """
        OBSが実際にストリームを開始するまで待機します。
        """
        logger.info(f"OBSがストリームを開始するのを最大{timeout}秒間待機します。")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                status = self.client.get_stream_status()
                if status and status.output_active:
                    logger.info("OBSがストリームを正常に開始しました。")
                    return True
            except Exception as e:
                logger.error(f"ストリームステータスの取得中にエラーが発生しました: {e}", exc_info=True)
                # 接続エラーの可能性があるため、デコレータに処理を任せるために再raiseする
                raise
            time.sleep(self.settings['obs_execution']['stream_status_polling_interval_seconds'])
        logger.warning(f"{timeout}秒以内にOBSがストリームを開始しませんでした。")
        return False

    @ensure_connection
    def reload_source(self, source_name, scene_name=None):
        """
        指定されたOBSソースを再読み込みします。
        """
        try:
            target_scene = scene_name
            if target_scene is None:
                current_scene_response = self.client.get_current_program_scene()
                target_scene = current_scene_response.current_program_scene_name
                logger.debug(f"シーン名が指定されなかったため、現在アクティブなシーン '{target_scene}' を対象とします。")

            logger.info(f"シーン '{target_scene}' 内のソース '{source_name}' の再読み込みを試行中...")
            response = self.client.get_input_settings(source_name)
            current_settings = response.input_settings
            input_kind = response.input_kind

            if input_kind == "browser_source":
                self.client.press_input_properties_button(source_name, property_name="refreshnocache")
                logger.info(f"ブラウザソース '{source_name}' (シーン: '{target_scene}') を再読み込みしました。")
            elif "local_file" in current_settings:
                file_path = current_settings['local_file']
                self.client.set_input_settings(source_name, {"local_file": file_path}, overlay=True)
                logger.info(f"メディアソース '{source_name}' (シーン: '{target_scene}') を設定再適用により再読み込みしました。")
            else:
                logger.warning(f"ソース '{source_name}' (シーン: '{target_scene}') はブラウザソースでもメディアソースでもないため、一般的な再読み込み方法を試行します。")
                self.client.set_input_settings(source_name, current_settings, overlay=True)
                logger.info(f"ソース '{source_name}' (シーン: '{target_scene}') を設定再適用により再読み込みしました。")

            return True
        except Exception as e:
            logger.error(f"ソース '{source_name}' の再読み込み中に予期せぬエラー: {e}", exc_info=True)
            return False
