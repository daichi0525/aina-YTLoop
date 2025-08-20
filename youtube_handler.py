import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
import pytz
import yaml
from logger import logger # ロガーをインポート

SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']

def get_authenticated_service(settings):
    credentials = None
    # token.pickle が存在すれば、保存された認証情報を使用
    if os.path.exists(settings['youtube']['token_pickle_file']):
        with open(settings['youtube']['token_pickle_file'], 'rb') as token:
            credentials = pickle.load(token)

    # 認証情報がない、または期限切れの場合、再認証
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(settings['youtube']['client_secrets_file'], SCOPES)
            credentials = flow.run_local_server(port=0)
        # 認証情報を保存
        with open(settings['youtube']['token_pickle_file'], 'wb') as token:
            pickle.dump(credentials, token)

    return build('youtube', 'v3', credentials=credentials)

def get_or_create_playlist(youtube, playlist_title, settings):
    """指定されたタイトルのプレイリストを検索し、なければ作成してIDを返す"""
    logger.info(f"プレイリスト '{playlist_title}' を検索中...")
    try:
        # 既存のプレイリストを検索
        # playlists().list には q パラメータがないため、mine=True で全て取得し、タイトルでフィルタリング
        next_page_token = None
        while True:
            response = youtube.playlists().list(
                part='id,snippet',
                mine=True,
                maxResults=50, # ページングで取得
                pageToken=next_page_token
            ).execute()

            for item in response.get('items', []):
                if item['snippet']['title'] == playlist_title:
                    logger.info(f"  - 既存のプレイリスト '{playlist_title}' (ID: {item['id']}) を見つけました。")
                    return item['id']

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

        # プレイリストが見つからなければ作成
        logger.info(f"  - プレイリスト '{playlist_title}' が見つかりませんでした。新しく作成します。")
        playlist_body = {
            'snippet': {
                'title': playlist_title,
                'description': settings['youtube']['playlist']['description_format'].format(playlist_title=playlist_title),
                'defaultLanguage': settings['youtube']['playlist']['default_language']
            },
            'status': {
                'privacyStatus': settings['youtube']['playlist']['default_privacy_status'] # プレイリストは非公開で作成
            }
        }
        response = youtube.playlists().insert(
            part='snippet,status',
            body=playlist_body
        ).execute()
        logger.info(f"  - 新しいプレイリスト '{playlist_title}' (ID: {response['id']}) を作成しました。")
        return response['id']

    except Exception as e:
        logger.error(f"  - エラー: プレイリストの検索または作成に失敗しました: {e}")
        return None

def delete_all_scheduled_broadcasts(youtube):
    logger.info("既存の予定されている配信枠を全て削除します...")
    try:
        # 予定されている配信枠をリスト
        all_broadcast_ids = []
        next_page_token = None
        while True:
            response = youtube.liveBroadcasts().list(
                part='id',
                broadcastStatus='upcoming',
                maxResults=50, # 最大50件取得
                pageToken=next_page_token
            ).execute()

            for item in response.get('items', []):
                all_broadcast_ids.append(item['id'])

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

        if not all_broadcast_ids:
            logger.info("  - 削除する予定されている配信枠はありませんでした。")
            return

        logger.info(f"  - {len(all_broadcast_ids)}件の予定されている配信枠を削除します。")
        for broadcast_id in all_broadcast_ids:
            logger.info(f"    - 配信枠 {broadcast_id} を削除中...")
            youtube.liveBroadcasts().delete(id=broadcast_id).execute()
            logger.info(f"    - 配信枠 {broadcast_id} を削除しました。")
        logger.info("  - 全ての予定されている配信枠の削除が完了しました。")

    except Exception as e:
        logger.error(f"  - エラー: 予定されている配信枠の削除中にエラーが発生しました: {e}")

def delete_all_live_streams(youtube):
    logger.info("既存のライブストリームを全て削除します...")
    try:
        all_stream_ids = []
        next_page_token = None
        while True:
            response = youtube.liveStreams().list(
                part='id',
                mine=True,
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            for item in response.get('items', []):
                all_stream_ids.append(item['id'])

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

        if not all_stream_ids:
            logger.info("  - 削除するライブストリームはありませんでした。")
            return

        logger.info(f"  - {len(all_stream_ids)}件のライブストリームを削除します。")
        for stream_id in all_stream_ids:
            logger.info(f"    - ストリーム {stream_id} を削除中...")
            try:
                youtube.liveStreams().delete(id=stream_id).execute()
                logger.info(f"    - ストリーム {stream_id} を削除しました。")
            except HttpError as e:
                if e.resp.status == 403 and "liveStreamDeletionNotAllowed" in str(e):
                    logger.warning(f"    - 警告: ストリーム {stream_id} は現在削除できません (Stream deletion is not allowed)。スキップします。")
                else:
                    logger.error(f"    - エラー: ストリーム {stream_id} の削除中に予期せぬエラーが発生しました: {e}")
        logger.info("  - 全てのライブストリームの削除が完了しました。")

    except Exception as e:
        logger.error(f"  - エラー: ライブストリームの削除中にエラーが発生しました: {e}")

def create_youtube_broadcast(youtube, settings):
    """
    YouTubeに新しいライブ配信枠を作成し、ストリームキーを返します。
    config.pyの設定を使用します。
    """
    if settings['youtube']['cleanup_old_broadcasts']:
        # 既存の予定されている配信枠を削除
        delete_all_scheduled_broadcasts(youtube)

        # 既存のライブストリームを全て削除
        delete_all_live_streams(youtube)
    else:
        logger.info("既存の配信枠とストリームの削除はスキップされました。")

    utc_now = datetime.utcnow().replace(tzinfo=pytz.utc)
    jst = pytz.timezone('Asia/Tokyo')
    now_jst = utc_now.astimezone(jst)

    # タイトル生成
    # TODO: countのロジックを実装
    broadcast_count = 1 # 仮の値
    title = settings['youtube']['broadcast']['title_format'].format(
        date=now_jst.strftime("%Y-%m-%d"),
        time=now_jst.strftime("%H:%M:%S"),
        count=broadcast_count
    )

    # 1. ライブ配信枠(Broadcast)を作成
    logger.info("1. 新しいライブ配信枠を作成します...")
    broadcast_body = {
        'snippet': {
            'title': title,
            'description': settings['youtube']['broadcast']['description'],
            'scheduledStartTime': (utc_now + timedelta(seconds=settings['youtube']['create']['start_time_buffer_seconds'])).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'scheduledEndTime': (utc_now + timedelta(seconds=settings['youtube']['broadcast']['scheduled_duration_seconds'])).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'categoryId': settings['youtube']['broadcast']['category_id'],
            'tags': settings['youtube']['broadcast']['tags'],
        },
        'status': {
            'privacyStatus': settings['youtube']['broadcast']['privacy_status'],
            'selfDeclaredMadeForKids': settings['youtube']['broadcast']['made_for_kids'],
        },
        'contentDetails': {
            'enableAutoStart': settings['youtube']['broadcast']['enable_auto_start'],
            'enableAutoStop': settings['youtube']['broadcast']['enable_auto_stop'],
            'latencyPreference': settings['youtube']['broadcast']['latency_preference'],
            'enableDvr': settings['youtube']['broadcast']['enable_dvr'],
            'enableLiveChat': settings['youtube']['broadcast']['enable_live_chat'],
            'recordFromStart': settings['youtube']['broadcast']['record_from_start'],
            'enableArchive': settings['youtube']['broadcast']['enable_archive'],
        }
    }
    try:
        broadcast_insert_response = youtube.liveBroadcasts().insert(
            part='snippet,status,contentDetails',
            body=broadcast_body
        ).execute()
        broadcast_id = broadcast_insert_response['id']
        logger.info(f"  - 配信枠を作成しました (ID: {broadcast_id})")
    except Exception as e:
        logger.error(f"  - エラー: 配信枠の作成に失敗しました: {e}")
        return None

    # 2. ライブストリーム(Stream)を作成
    #    常に新しいストリームを作成します。
    logger.info("2. 新しいライブストリームを作成します...")
    try:
        stream_body = {
            "snippet": {
                "title": settings['youtube']['create']['stream_title_format'].format(datetime=utc_now.strftime('%Y-%m-%d %H:%M:%S'))
            },
            "cdn": {
                "frameRate": settings['youtube']['create']['stream_frame_rate'],
                "ingestionType": settings['youtube']['stream']['ingestion_type'],
                "resolution": settings['youtube']['stream']['format']
            }
        }
        stream_insert_response = youtube.liveStreams().insert(
            part="snippet,cdn",
            body=stream_body
        ).execute()
        stream_id = stream_insert_response['id']
        stream_name = stream_insert_response['cdn']['ingestionInfo']['streamName']
        logger.info(f"  - 新しいストリームを作成しました (ID: {stream_id})")

    except Exception as e:
        logger.error(f"  - エラー: ストリームの作成に失敗しました: {e}")
        return None

    # 3. 配信枠とストリームを紐付け(Bind)
    logger.info("3. 配信枠とストリームを紐付けます...")
    try:
        youtube.liveBroadcasts().bind(
            part='id,snippet,contentDetails',
            id=broadcast_id,
            streamId=stream_id
        ).execute()
        logger.info("  - 紐付けに成功しました。")
    except Exception as e:
        logger.error(f"  - エラー: 紐付けに失敗しました: {e}")
        return None

    # 4. プレイリストに追加
    playlist_title = utc_now.strftime(settings['youtube']['broadcast']['playlist_title_format'])
    playlist_id = get_or_create_playlist(youtube, playlist_title, settings)
    if playlist_id:
        logger.info(f"4. 配信枠をプレイリスト '{playlist_title}' に追加します...")
        try:
            playlist_item_body = {
                'snippet': {
                    'playlistId': playlist_id,
                    'resourceId': {
                        'kind': 'youtube#video',
                        'videoId': broadcast_id
                    }
                }
            }
            youtube.playlistItems().insert(
                part='snippet',
                body=playlist_item_body
            ).execute()
            logger.info("  - プレイリストへの追加に成功しました。")
        except Exception as e:
            logger.error(f"  - エラー: プレイリストへの追加に失敗しました: {e}")
    else:
        logger.info("  - プレイリストが見つからないか作成できなかったため、追加をスキップします。")

    logger.info(f"\nストリームキー: {stream_name}")
    return stream_name


def get_live_broadcast_status(youtube, broadcast_id):
    """指定されたライブ配信枠のステータスを取得します。"""
    try:
        response = youtube.liveBroadcasts().list(
            part='status',
            id=broadcast_id
        ).execute()
        if response and 'items' in response and len(response['items']) > 0:
            return response['items'][0]['status']['lifeCycleStatus']
        return None
    except Exception as e:
        logger.error(f"ライブ配信枠のステータス取得中にエラーが発生しました: {e}")
        return None

def transition_broadcast_status(youtube, broadcast_id, status):
    """ライブ配信枠のステータスを遷移させます。"""
    try:
        youtube.liveBroadcasts().transition(
            part='status',
            id=broadcast_id,
            broadcastStatus=status
        ).execute()
        logger.info(f"ライブ配信枠 {broadcast_id} のステータスを {status} に遷移しました。")
        return True
    except Exception as e:
        logger.error(f"ライブ配信枠 {broadcast_id} のステータス遷移中にエラーが発生しました: {e}")
        return False