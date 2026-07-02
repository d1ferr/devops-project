import re, glob, os, logging
import psycopg2
import paramiko
import telebot
from telebot import types

# ----------------------- НАСТРОЙКИ -----------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8287749023:AAGwckt_5nntdCQ6l1BCqi0QGoVeuCNj6eA")

# SSH подключение к удалённой машине
SSH_HOST = os.getenv("SSH_HOST", "192.168.1.111")
SSH_PORT = int(os.getenv("SSH_PORT", 22))
SSH_USER = os.getenv("SSH_USER", "root")
SSH_PASSWORD = os.getenv("SSH_PASSWORD", "admin")

# БД PostgreSQL
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "repl_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres"),
}

LOG_DIR = os.getenv("LOG_DIR", "/var/log/postgresql/")

REPL_KEYWORDS = [
    "replication", "walsender", "walreceiver", "standby",
    "streaming", "ready to accept", "start_replication",
    "received replication command",
]

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")
PASSWORD_RE = re.compile(r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*()]).{8,}$")

logging.basicConfig(
    filename="logfile.txt",
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(BOT_TOKEN)
user_data = {}


# ----------------------- SSH -----------------------
def ssh_command(command):
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=SSH_HOST, username=SSH_USER,
                       password=SSH_PASSWORD, port=SSH_PORT)
        stdin, stdout, stderr = client.exec_command(command)
        data = stdout.read().decode("utf-8", "ignore") + stderr.read().decode("utf-8", "ignore")
        client.close()
        return data.strip() or "(пустой ответ)"
    except Exception as e:
        logger.error(f"Ошибка SSH: {e}")
        return f"Ошибка подключения: {e}"


def reply_long(chat_id, text):
    for i in range(0, len(text), 3500):
        bot.send_message(chat_id, text[i:i + 3500])


# ----------------------- БД -----------------------
def db_query(sql, params=None, fetch=False):
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if fetch:
                    return cur.fetchall()
    finally:
        conn.close()


# ----------------------- /start /help -----------------------
@bot.message_handler(commands=["start"])
def start(msg):
    bot.send_message(msg.chat.id, f"Привет {msg.from_user.full_name}!")


@bot.message_handler(commands=["help"])
def help_cmd(msg):
    bot.send_message(msg.chat.id,
        "Поиск и БД:\n"
        "/find_email — найти email в тексте и записать в БД\n"
        "/find_phone_number — найти телефоны в тексте и записать в БД\n"
        "/verify_password — проверка сложности пароля\n"
        "/get_emails — email из БД\n"
        "/get_phone_numbers — телефоны из БД\n"
        "/get_repl_logs — логи репликации\n\n"
        "Мониторинг:\n"
        "/get_release /get_uname /get_uptime\n"
        "/get_df /get_free /get_mpstat /get_w\n"
        "/get_auths /get_critical /get_ps /get_ss\n"
        "/get_apt_list /get_services")


# ----------------------- ЛОГИ РЕПЛИКАЦИИ -----------------------
@bot.message_handler(commands=["get_repl_logs"])
def get_repl_logs(msg):
    db_master_host = os.getenv("DB_HOST", "192.168.1.115")
    cmd = (
        f"sudo bash -c \"grep -iE '{'|'.join(REPL_KEYWORDS)}' "
        f"/var/log/postgresql/postgresql-*.log 2>/dev/null | tail -30\""
    )
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=db_master_host, username="ansible",
                       password="ansible", port=22)
        stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
        stdin.write("ansible\n")
        stdin.flush()
        data = stdout.read().decode("utf-8", "ignore")
        client.close()
    except Exception as e:
        bot.send_message(msg.chat.id, f"Ошибка подключения к master БД: {e}")
        return

    if not data.strip():
        bot.send_message(msg.chat.id, "Строк о репликации не найдено.")
        return
    reply_long(msg.chat.id, data.strip())

# ----------------------- ДАННЫЕ ИЗ БД -----------------------
@bot.message_handler(commands=["get_emails"])
def get_emails(msg):
    rows = db_query("SELECT id, email FROM emails ORDER BY id;", fetch=True)
    if not rows:
        bot.send_message(msg.chat.id, "Таблица emails пуста.")
        return
    bot.send_message(msg.chat.id, "\n".join("{}. {}".format(r[0], r[1]) for r in rows))


@bot.message_handler(commands=["get_phone_numbers"])
def get_phone_numbers(msg):
    rows = db_query("SELECT id, phone_number FROM phones ORDER BY id;", fetch=True)
    if not rows:
        bot.send_message(msg.chat.id, "Таблица phones пуста.")
        return
    bot.send_message(msg.chat.id, "\n".join("{}. {}".format(r[0], r[1]) for r in rows))


# ----------------------- ПОИСК EMAIL + ЗАПИСЬ В БД -----------------------
@bot.message_handler(commands=["find_email"])
def find_email_cmd(msg):
    user_data[msg.chat.id] = {"mode": "email"}
    bot.send_message(msg.chat.id, "Введите текст для поиска email-адресов:")
    bot.register_next_step_handler(msg, process_find_text)


# ----------------------- ПОИСК ТЕЛЕФОНОВ + ЗАПИСЬ В БД -----------------------
@bot.message_handler(commands=["find_phone_number"])
def find_phone_cmd(msg):
    user_data[msg.chat.id] = {"mode": "phone"}
    bot.send_message(msg.chat.id, "Введите текст для поиска телефонных номеров:")
    bot.register_next_step_handler(msg, process_find_text)


def process_find_text(msg):
    data = user_data.get(msg.chat.id, {})
    mode = data.get("mode", "email")
    text = msg.text or ""

    if mode == "email":
        found = EMAIL_RE.findall(text)
    else:
        found = [m.strip() for m in PHONE_RE.findall(text)]

    found = list(dict.fromkeys(found))

    if not found:
        bot.send_message(msg.chat.id, "Ничего не найдено.")
        return

    data["found"] = found
    listing = "\n".join(f"{i+1}. {v}" for i, v in enumerate(found))

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Записать в БД", callback_data="save"),
        types.InlineKeyboardButton("Отказаться", callback_data="cancel"))
    bot.send_message(msg.chat.id, f"Найдено:\n{listing}\n\nЗаписать в базу данных?",
                     reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data in ["save", "cancel"])
def callback_handler(call):
    data = user_data.get(call.message.chat.id, {})
    found = data.get("found", [])
    mode = data.get("mode", "email")

    if call.data == "cancel":
        bot.edit_message_text("Запись отменена.", call.message.chat.id, call.message.message_id)
        return

    saved, errors = 0, 0
    for value in found:
        try:
            if mode == "email":
                db_query("INSERT INTO emails (email) VALUES (%s);", (value,))
            else:
                db_query("INSERT INTO phones (phone_number) VALUES (%s);", (value,))
            saved += 1
        except Exception:
            errors += 1

    bot.edit_message_text(f"Готово. Записано: {saved}. Ошибок: {errors}.",
                         call.message.chat.id, call.message.message_id)


# ----------------------- ПРОВЕРКА ПАРОЛЯ -----------------------
@bot.message_handler(commands=["verify_password"])
def verify_password_cmd(msg):
    user_data[msg.chat.id] = {"mode": "password"}
    bot.send_message(msg.chat.id, "Введите пароль для проверки:")
    bot.register_next_step_handler(msg, process_password)


def process_password(msg):
    if PASSWORD_RE.match(msg.text):
        bot.send_message(msg.chat.id, "Пароль сложный ✅")
    else:
        bot.send_message(msg.chat.id, "Пароль простой ❌")


# ----------------------- МОНИТОРИНГ (SSH) -----------------------
@bot.message_handler(commands=["get_release"])
def cmd_release(msg):  reply_long(msg.chat.id, ssh_command("cat /etc/*release"))

@bot.message_handler(commands=["get_uname"])
def cmd_uname(msg):    reply_long(msg.chat.id, ssh_command("uname -a"))

@bot.message_handler(commands=["get_uptime"])
def cmd_uptime(msg):   reply_long(msg.chat.id, ssh_command("uptime"))

@bot.message_handler(commands=["get_df"])
def cmd_df(msg):       reply_long(msg.chat.id, ssh_command("df -h"))

@bot.message_handler(commands=["get_free"])
def cmd_free(msg):     reply_long(msg.chat.id, ssh_command("free -h"))

@bot.message_handler(commands=["get_mpstat"])
def cmd_mpstat(msg):   reply_long(msg.chat.id, ssh_command("mpstat"))

@bot.message_handler(commands=["get_w"])
def cmd_w(msg):        reply_long(msg.chat.id, ssh_command("w"))

@bot.message_handler(commands=["get_auths"])
def cmd_auths(msg):    reply_long(msg.chat.id, ssh_command("last -n 10"))

@bot.message_handler(commands=["get_critical"])
def cmd_critical(msg): reply_long(msg.chat.id, ssh_command("journalctl -p crit -n 5 --no-pager"))

@bot.message_handler(commands=["get_ps"])
def cmd_ps(msg):       reply_long(msg.chat.id, ssh_command("ps aux | head -n 20"))

@bot.message_handler(commands=["get_ss"])
def cmd_ss(msg):       reply_long(msg.chat.id, ssh_command("ss -tuln"))

@bot.message_handler(commands=["get_services"])
def cmd_services(msg): reply_long(msg.chat.id, ssh_command("systemctl list-units --type=service --state=running --no-pager"))


# ----------------------- APT LIST -----------------------
@bot.message_handler(commands=["get_apt_list"])
def apt_list_cmd(msg):
    bot.send_message(msg.chat.id, "Введите название пакета или 'все' для вывода всех:")
    bot.register_next_step_handler(msg, process_apt_list)


def process_apt_list(msg):
    text = msg.text.strip()
    if text.lower() in ("все", "all"):
        reply_long(msg.chat.id, ssh_command("apt list --installed 2>/dev/null"))
    else:
        reply_long(msg.chat.id, ssh_command(f"apt list --installed 2>/dev/null | grep -i {text}"))


# ----------------------- ЭХО -----------------------
@bot.message_handler(func=lambda m: True)
def echo(msg):
    bot.send_message(msg.chat.id, msg.text)


# ----------------------- ЗАПУСК -----------------------
logger.info("Бот запущен")
print("Бот запущен. Ctrl+C для остановки.")
bot.infinity_polling()
