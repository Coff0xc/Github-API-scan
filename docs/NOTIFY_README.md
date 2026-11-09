# Notifications

When a check on an authorized target comes back `valid` or `quota_exceeded`, the scanner can tell you where it was. The message is four lines: platform, masked preview, location, and a reminder that the notice has no full key and no balance. If a channel accepts that message, the row's disposition becomes `notified`.

Nothing is sent when no channel is configured. The scanner does not create a desktop file of raw keys by itself.

## Channels

Set one of these, or copy `notify_config.example.yaml` to `notify_config.yaml` and turn a channel on. `NOTIFY_CONFIG` can point at another path.

| Variable | Channel |
| --- | --- |
| `DISCORD_WEBHOOK` | Discord incoming webhook |
| `SLACK_WEBHOOK` | Slack incoming webhook |
| `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` | Telegram bot |
| `FEISHU_WEBHOOK` | Feishu custom bot |
| `DINGTALK_WEBHOOK` | DingTalk custom bot. `DINGTALK_SECRET` is the optional sign secret |
| `SERVERCHAN_KEY` | ServerChan |
| `BARK_DEVICE_KEY` | Bark on iOS |

The example file also has a file channel and a sound channel. They are off until you enable them. The file channel writes the same four-line notice, not the key.

```bash
export DISCORD_WEBHOOK="https://discord.com/api/webhooks/xxx/xxx"
python main_v2.2.py --authorized --target-org your-org
```

```bash
cp notify_config.example.yaml notify_config.yaml
python test_notifier.py --config notify_config.yaml --channel discord
```

`test_notifier.py` can still build sample messages at several severities. Those samples are for the channel test. A real scan does not include a balance or a model tier in the text that goes out.

## What still filters a notice

The body is always the disclosure notice. Around it, the notifier still applies three gates:

- The same key is not sent twice in one process.
- Quiet hours, when enabled in `notify_config.yaml`, skip non-critical notices. A scan notice is not critical.
- The rate limit, when enabled, defaults to 30 notices per 60 seconds.

Each channel has `min_severity`. The example file uses `medium`. A finding that carries no balance and no model tier is treated as medium, so the example config lets it through. A channel set to `high` will not hear ordinary scan notices. `quota` in a stored balance string is the case that stays low.

`rotated` is never set by the notifier. That mark is yours, after the key is revoked:

```bash
python main_v2.2.py --set-disposition <64-hex-fingerprint> rotated
```

## Where to hook it

The scan calls `disclose_finding` in `notify_integration.py` after validation. That is the path to extend. `notify_key_found` and `patch_validator_for_notifications` are older helpers. They still end in a masked send, but they are not what `main_v2.2.py` uses, and the snippets that pass a balance or `is_high_value` do not change the text that leaves the machine.

## Setting up a webhook

Discord: Server Settings → Integrations → Webhooks → New Webhook → copy the URL.

Telegram: talk to [@BotFather](https://t.me/BotFather), send `/newbot`, keep the token. Message your bot once, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `chat.id`.

Feishu: group settings → Bots → Custom Bot → copy the webhook.

DingTalk: group settings → Smart Assistant → Custom bot. Prefer the sign-secret option, and put that secret in `DINGTALK_SECRET` or the `secret` field.

## If nothing arrives

The scan only notifies `valid` and `quota_exceeded`. An invalid key stays quiet. A missing webhook stays quiet and leaves the row `open`. A channel whose `min_severity` is `high` also stays quiet for a normal finding.

Check the webhook with `python test_notifier.py --channel <name>`. Then check quiet hours and the rate limit in the yaml. Dedup is in memory for the process. A new process can send the same key again. The disposition on the row, once `notified`, is the record that a person already heard about it.
