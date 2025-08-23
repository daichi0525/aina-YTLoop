# aina-YTLoop: 24時間YouTubeライブ配信自動化

## プロジェクト概要

`aina-YTLoop`は、YouTubeでの24時間ライブ配信を自動化するために設計された堅牢なPythonベースのソリューションです。OBS (Open Broadcaster Software) とシームレスに統合し、YouTube Data API v3を活用することで、継続的なライブ配信を効率的に管理します。8時間ごと（設定可能）に自動的にストリームを開始および停止し、新しいブロードキャストイベントを作成することで、YouTubeのライブ配信ガイドラインを遵守しつつ、中断のないコンテンツ配信を保証します。

## 主な機能

*   **ライブ配信の自動化:** YouTubeライブブロードキャストのライフサイクルを管理します。
*   **OBS連携:** WebSocketを介してOBS Studioを制御し、ストリームの開始と終了を行います。
    *   **設定可能なパラメータ:** OBS接続、YouTubeブロードキャストの詳細、プレイリスト管理に関するすべての重要なパラメータは`config.yaml`に外部化されています。
*   **動的なストリームタイトル:** タイムスタンプ付きのストリームタイトルを自動生成します。
*   **プレイリスト管理:** 過去のブロードキャストを月ごとのプレイリストに整理します。
*   **エラーハンドリング:** APIインタラクションとOBS接続に関する基本的なエラーハンドリングが含まれています。
*   **ログ出力:** ログファイルを自動生成し、運用状況を記録します。
*   **ストリーム監視と自動復旧:** 指定時間おきにOBSまたはYouTubeでの配信状況を監視し、停止している場合は自動的に次の処理へ移行します。
*   **OBSソースの再読み込み:** 指定時間おきにOBSの対象ソースを再読み込みし、表示の安定性を保ちます。

## 動作原理

`YTLoop`は、以下のモジュールと設定ファイルによって構成され、連携して動作します。

-   **`main.py`**: アプリケーションのエントリーポイントであり、全体の制御ロジックを担います。YouTube認証、OBS接続、そして指定されたスケジュールに基づいた配信開始、ループ再生、配信終了のフローを管理します。
-   **`youtube_handler.py`**: YouTube Data API v3とのインターフェースを提供します。OAuth2.0認証フローを処理し、ライブ配信の作成、更新、削除、動画情報の取得といったYouTube関連の操作を実行します。
-   **`obs_handler.py`**: `obs-websocket-py`ライブラリを使用してOBS StudioとWebSocketで通信します。OBSのシーン切り替え、配信開始/停止、ソースの表示/非表示など、OBS Studioの様々な操作をプログラムから実行できるようにします。
-   **`config.yaml`**: プロジェクトの設定情報（YouTube APIのスコープ、OBSの接続情報、ループ再生する動画ID、配信タイトル、配信スケジュールなど）を一元的に管理します。

## ディレクトリ構成

プロジェクトの主要なファイルとディレクトリは以下の通りです。

```
./aina-YTLoop
├── config.yaml           # 各種設定ファイル（OBS接続情報、YouTube API設定など）
├── main.py               # メインスクリプト。アプリケーションのエントリーポイント
├── obs_handler.py        # OBS Studioとの連携を処理するスクリプト
├── youtube_handler.py    # YouTube Data APIとの連携を処理するスクリプト
├── requirements.txt      # プロジェクトの依存関係リスト
├── client_secret.json    # YouTube API認証情報（Google Cloudからダウンロード）
├── token.pickle          # YouTube API認証トークン（初回実行時に自動生成）
└── README.md             # このドキュメント
```

ユーザーが直接編集する可能性が高いのは `config.yaml` です。`client_secret.json` はGoogle Cloudからダウンロードして配置します。`token.pickle` は自動生成されるため、通常は触る必要はありません。

## 使用技術

*   Python 3.9以上
*   OBS WebSocket
*   YouTube Data API v3

## 前提条件

本プロジェクトを実行する前に、以下のソフトウェアがインストールされ、設定されていることを確認してください。

*   **Python 3.9以上:**
    *   macOSをご利用の場合は、[Homebrew](https://brew.sh/ja/) を使用してPythonをインストールすることを推奨します。
        ```bash
        brew install python
        ```
*   **OBS Studio:**
    *   [OBS (Open Broadcaster Software)](https://obsproject.com/ja) がPCにインストールされている必要があります。
    *   **OBS WebSocket設定:**
        *   OBS Studioの設定でWebSocketサーバーを有効にします（`ツール` -> `WebSocketサーバー設定`）。
        *   WebSocketサーバーのパスワードを設定します。
        *   ポート（デフォルトは`4455`）とパスワードが`config.yaml`の設定と一致していることを確認してください。

*   **YouTube Data APIアクセス:**
    *   YouTube Data API v3が有効になっているGoogle Cloudプロジェクトが必要です。
    *   Google Cloud Consoleから`client_secret.json`ファイルをダウンロードし、プロジェクトのルートディレクトリに配置してください。このファイルはYouTube APIとの認証に不可欠です。

## インストール

1.  **リポジトリをクローンします:**
    ```bash
    git clone https://github.com/2525aina/aina-YTLoop
    cd aina-YTLoop
    ```

2.  **Python仮想環境を作成します:**
    ```bash
    python3 -m venv venv
    ```

3.  **仮想環境をアクティブ化します:**
    *   macOS/Linux:
        ```bash
        source venv/bin/activate
        ```
    *   Windows:
        ```bash
        .\venv\Scripts\activate
        ```

4.  **依存関係をインストールします:**
    *   まず、pipを最新バージョンにアップグレードします。
        ```bash
        venv/bin/python3 -m pip install --upgrade pip
        ```
    *   次に、依存関係をインストールします。
        ```bash
        pip install -r requirements.txt
        ```

## 設定 (`config.yaml`)

`config.yaml`ファイルは、プロジェクトのすべての設定可能なパラメータを一元管理します。お使いの環境と好みに合わせてこれらの値を調整してください。

## 使用方法

1.  **仮想環境がアクティブであることを確認します。**
2.  **メインスクリプトを実行します:**
    ```bash
    python main.py
    # geminiでの実行方法
    source venv/bin/activate && python -m main
    ```
    スクリプトはYouTubeとの認証（`token.pickle`が存在しないか期限切れの場合）、OBSへの接続、新しいYouTubeライブブロードキャストの作成、およびストリームの管理を試行します。

## トラブルシューティング

*   **`HttpError 403: User requests exceed the rate limit.`**: これはYouTube Data APIの割り当てを超過したことを示します。割り当てがリセットされるのを待つか、Googleに増加をリクエストする必要があります。
*   **`ConnectionRefusedError: [Errno 61] Connection refused` (OBS):**
    *   OBS Studioが実行されており、WebSocketサーバーが有効になっていることを確認してください。
    *   `config.yaml`のOBS WebSocketポートとパスワードがOBSの設定と一致していることを確認してください。
    *   システムでOBSの起動に時間がかかる場合は、`config.yaml`の`OBS_LAUNCH_WAIT_SECONDS`を増やしてください。
    *   OBS Studioのログで詳細なエラーメッセージを確認してください。
*   **`SyntaxError: EOL while scanning string literal`**: これは通常、Pythonファイル内の文字列が適切に閉じられていないか、エスケープされていない改行が含まれていることを意味します。すべての文字列が正しく終了していることを確認してください。

## 貢献

自由にリポジトリをフォークし、改善を行い、プルリクエストを送信してください。

## ライセンス

*(ここにライセンス情報を追加してください。例: MITライセンス)*

## 一括コマンド！！

```sh
# Homebrew インストール
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
# Python インストール
brew install python
# リポジトリ クローン
git clone https://github.com/2525aina/aina-YTLoop
cd aina-YTLoop
# Python仮想環境 作成
python3 -m venv venv
# 仮想環境 アクティブ化
  # macOS/Linux:
source venv/bin/activate
  # Windows:
.\venv\Scripts\activate
# 依存関係 インストール
  # pip バージョン アップグレード
venv/bin/python3 -m pip install --upgrade pip
# 依存関係 インストール
pip install -r requirements.txt
# aina-YTLoop 開始
python main.py
# aina-YTLoop 強制停止
  # Ctrl+c

    # geminiでの実行方法
    # source venv/bin/activate && python -m main
```