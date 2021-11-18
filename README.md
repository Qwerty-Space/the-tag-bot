# The Tag Bot
@TheTagBot is a Telegram bot that lets you save and retrieve media using your own tags.

# Setup
If you want to host your own copy of this bot, here's how:
1. Get [Nix](https://nixos.org/download.html) running on your system (preferably use NixOS)
1. Install [Elasticsearch](https://www.elastic.co/)
1. Copy [secrets-example.py](secrets-example.py) to `secrets.py` and edit the `HTTP_PASS` variable to a secure password (for example `hunter2`), this is the password for the Elasticsearch user that the bot will use
1. Setup [security](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-minimal-setup.html) in Elasticsearch by putting the following into `$ES_PATH_CONF/elasticsearch.yml`:
    ```yaml
    xpack.security.enabled: true
    discovery.type: single-node
    ```
    Then run (as the same user that Elasticsearch runs as):
    ```shell
    elasticsearch-setup-passwords auto
    ```
    Put the generated password for the `elastic` user in `secrets.py`:
    ```python
    HTTP_PASS = '<super secret password that you generated earlier>'
    ADMIN_HTTP_PASS = 'elastic user password here'
    ```

1. Now you can run the bot using `nix-shell` in the repo root:
    ```
    nix-shell shell.nix --run 'python bot.py'
    ```
    The bot will take care of setting up the Elasticsearch indicies that it needs.

1. Telethon will prompt for your bot token when you first run the bot, when you move it to a server simply copy the `bot.session` file to the server.

# Config
You can change the limits in [constants.py](constants.py) to suit your needs.

# Development
When you want to make changes to the index mapping, you have to delete and re-create it with the new settings. The `scripts` directory has two scripts that can help with this:
- [backup.py](scripts/backup.py) makes the index read-only and copies all the documents into a backup index
- [recreate.py](scripts/recreate.py) deletes and re-creates the index with the settings in `settings.json`, then copies the documents from the backup (you can run this multiple times after having run backup.py once)
