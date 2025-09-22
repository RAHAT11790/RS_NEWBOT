# batch_update_pyrogram.py
import re
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, RPCError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ====== CONFIG: বদলে দিন ======
API_ID = 25976192           # my.telegram.org থেকে নেওয়া API_ID
API_HASH = "8ba23141980539b4896e5adbc4ffd2e2"
BOT_TOKEN = "8257089548:AAG3hpoUToom6a71peYep-DBfgPiKU3wPGE"  # @BotFather থেকে পাওয়া bot token
# ==============================

RS_USERNAMES = [None, None, None]  # আপনার সেট করা তিনটি ইউজারনেম

# ========== Helper functions ==========
def _normalize_username(u: str) -> str:
    if not u:
        return None
    u = u.strip()
    if u.startswith("@"):
        u = u[1:]
    u = re.sub(r"^https?://(?:www\.)?t\.me/", "", u, flags=re.IGNORECASE)
    u = re.sub(r"^t\.me/", "", u, flags=re.IGNORECASE)
    return u

def replace_all_usernames(text: str, new_usernames: list) -> str:
    if not text or not new_usernames or all(u is None for u in new_usernames):
        return text

    pattern = r'@[a-zA-Z0-9_]{1,32}|t\.me/[a-zA-Z0-9_]{1,32}|https?://(?:www\.)?t\.me/[a-zA-Z0-9_]{1,32}'
    matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))
    if not matches:
        return text

    result = []
    last_idx = 0
    for i, m in enumerate(matches):
        start, end = m.span()
        orig = m.group(0)
        result.append(text[last_idx:start])

        if i < len(new_usernames) and new_usernames[i]:
            newu = new_usernames[i]
            if orig.startswith("@"):
                replacement = f"@{newu}"
            elif orig.lower().startswith("t.me/"):
                replacement = f"t.me/{newu}"
            else:
                replacement = f"https://t.me/{newu}"
            result.append(replacement)
        else:
            result.append(orig)

        last_idx = end

    result.append(text[last_idx:])
    return "".join(result)

# ========== Pyrogram bot ==========
app = Client("rs_updater_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("set_rs") & filters.private)
async def cmd_set_rs(client, message):
    global RS_USERNAMES
    args = message.text.split()[1:]
    if not args or len(args) > 3:
        await message.reply_text("Usage: /set_rs username1 username2 username3 (up to 3)")
        return
    normalized = [_normalize_username(u) for u in args[:3]]
    normalized += [None] * (3 - len(normalized))
    RS_USERNAMES = normalized
    await message.reply_text(f"✅ RS set: @{RS_USERNAMES[0]} | @{RS_USERNAMES[1]} | @{RS_USERNAMES[2]}")

@app.on_message(filters.command("batch_update") & filters.private)
async def cmd_batch_update(client, message):
    if not RS_USERNAMES[0]:
        await message.reply_text("❌ Please set RS usernames first with /set_rs")
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.reply_text("Usage: /batch_update @channelusername message_count (e.g., /batch_update @chan 50)")
        return

    channel = parts[1].lstrip("@")
    try:
        total_count = int(parts[2])
    except ValueError:
        await message.reply_text("❌ message_count must be a number.")
        return

    if total_count > 5000:
        await message.reply_text("❌ Too many messages at once. Try <= 5000.")
        return

    await message.reply_text(f"🔄 Starting: scanning last {total_count} messages in @{channel} ...")

    try:
        me = await client.get_me()
        member = await client.get_chat_member(channel, me.id)
        if member.status not in ("administrator", "creator"):
            await message.reply_text("❌ Bot is not an admin in that channel.")
            return
        if hasattr(member, "privileges") and member.privileges:
            if getattr(member.privileges, "can_edit_messages", None) is False:
                await message.reply_text("❌ Bot admin does not have can_edit_messages permission.")
                return
    except RPCError as e:
        await message.reply_text(f"❌ Failed to check admin status: {e}")
        return

    processed = 0
    edited = 0
    skipped = 0

    try:
        async for msg in client.get_chat_history(channel, limit=total_count):
            processed += 1
            old_text = msg.text or msg.caption or ""
            if not old_text.strip():
                skipped += 1
                continue

            new_text = replace_all_usernames(old_text, RS_USERNAMES)
            if new_text == old_text:
                skipped += 1
            else:
                try:
                    if msg.text:
                        await client.edit_message_text(chat_id=channel, message_id=msg.message_id, text=new_text)
                    elif msg.caption:
                        await client.edit_message_caption(chat_id=channel, message_id=msg.message_id, caption=new_text)
                    edited += 1
                except Exception as e:
                    logger.error(f"Error editing message {msg.message_id}: {e}")

            await asyncio.sleep(0.7)
            if processed % 50 == 0:
                await message.reply_text(f"Progress: processed {processed}/{total_count}, edited {edited} so far...")

            if processed >= total_count:
                break

        await message.reply_text(f"✅ Done. Processed: {processed}, Edited: {edited}, Skipped: {skipped}")
    except Exception as e:
        logger.exception("Batch update failed")
        await message.reply_text(f"❌ Batch update failed: {e}")

if __name__ == "__main__":
    print("Bot is starting...")
    app.run()
