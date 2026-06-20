import os
import json
import asyncio
from typing import Optional, List
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import socketio

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

BOT_TOKEN = os.getenv("BOT_TOKEN")

DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "data.json")
MEDIA_DIR = "media"
R1_DIR = "round1"

app = FastAPI()
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
socket_app = socketio.ASGIApp(sio, app)

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(R1_DIR, exist_ok=True)

app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
app.mount("/r1img", StaticFiles(directory=R1_DIR), name="r1img")

# --- DATA ---

DEFAULT_DATA = {
    "players": {},
    "round1": {
        "photos": {str(i): {"correct": "artem"} for i in range(1, 11)}
    },
    "round2": {
        "questions": [
            {
                "id": 1,
                "text": "Биоконструкт, экстрагированный из остеоцитарного матрикса первичного субъекта, лишённый пупочной маркировки, вступивший в семиотический контакт с чешуйчатым таксоном, инициировавший вегетативную дегустацию, повлёкшую дермальную дисрегуляцию, текстильную имплантацию и принудительную релокацию за экватор замкнутой экосистемы",
                "accepted": ["кот", "котёнок", "кошка"],
                "reader_tg_id": None
            },
            {
                "id": 3,
                "text": "Периферический кинетический трансдьюсер, интегрирующий монококовую рамную структуру с вариабельным сечением из углерод-эпоксидного ламината, оснащённый системой из ароматического полиамида, демонстрирующей нелинейную вязкоупругую гистерезисную петлю, сопряжённый с эргономичным грип-элементом со спиральной намоткой, амортизирующим резонансные колебания, при этом вектор приложенной силы модулируется в трёх плоскостях для достижения оптимальной трансляции момента инерции",
                "accepted": ["ракетка", "теннисная ракетка", "теннис"],
                "reader_tg_id": None
            },
            {
                "id": 4,
                "text": "Междисциплинарная прикладная практика, основанная на термодинамической трансформации органических субстратов и гидроколлоидных систем с использованием фазовых переходов, окислительно-восстановительных реакций и ферментативного гидролиза, включающая гомогенизацию, эмульсификацию и желатинизацию компонентов, с применением методов теплопередачи и механической деструкции тканей, направленная на модификацию органолептических характеристик",
                "accepted": ["кулинария", "готовка", "приготовление еды", "готовить"],
                "reader_tg_id": None
            },
            {
                "id": 5,
                "text": "Пищевой композит, полученный высокотемпературной экструзией крахмалсодержащего сырья с формированием аэрированной пористой матрицы, поверхностно модифицированной многокомпонентной органолептической системой, включающей протеолизаты, липидные эмульгаторы и азохромофорные красители с коротковолновой абсорбцией. Продукт отличается низкой гигроскопичностью и способностью к мгновенной десорбции летучих ароматических соединений при гидратации, что инициирует нейрохимический каскад в лимбических структурах",
                "accepted": ["чипсы", "попкорн", "сухарики", "кукурузные палочки"],
                "reader_tg_id": None
            },
            {
                "id": 6,
                "text": "Монолитный глиссирующий декинг с анизотропной структурой и многослойной архитектурой, оснащённый периферийными металлокерамическими упрочнителями для дискретного фрикционного взаимодействия с плотной криогенной средой, а также антропометрическими ретенционными узлами с эксцентриковыми зажимами, позволяющими трансформировать мышечно-скелетные импульсы в управляемую прецессию оси вращения в условиях переменной дисперсности подстилающего слоя",
                "accepted": ["сноуборд"],
                "reader_tg_id": None
            }
        ]
    }
}


class DataManager:
    def __init__(self):
        self.data = json.loads(json.dumps(DEFAULT_DATA))
        self.load()

    def load(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                try:
                    loaded = json.load(f)
                    self.data["players"] = loaded.get("players", {})
                    if "round1" in loaded:
                        self.data["round1"]["photos"].update(
                            loaded["round1"].get("photos", {})
                        )
                    if "round2" in loaded:
                        for i, q in enumerate(loaded["round2"].get("questions", [])):
                            if i < len(self.data["round2"]["questions"]):
                                self.data["round2"]["questions"][i].update(q)
                except Exception as e:
                    print(f"Data load error: {e}")

    def save(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get_leaderboard(self):
        players = []
        for tg_id, p in self.data["players"].items():
            r1 = p.get("score_r1", 0)
            r2 = p.get("score_r2", 0)
            players.append({
                "tg_id": tg_id,
                "name": p["name"],
                "r1": r1,
                "r2": r2,
                "total": r1 + r2
            })
        return sorted(players, key=lambda x: x["total"], reverse=True)


db = DataManager()

r1_state = {"current_photo": None, "votes": {}, "status": "idle"}
r2_state = {"current_q_idx": None, "player_answers": {}, "status": "idle"}
awaiting_name: dict = {}


# --- SOCKET ---

@sio.event
async def connect(sid, environ):
    await sio.emit("sync_state", build_full_state(), to=sid)


def build_full_state():
    return {
        "r1": {
            "status": r1_state["status"],
            "current_photo": r1_state["current_photo"],
            "vote_counts": get_r1_vote_counts(),
        },
        "r2": {
            "status": r2_state["status"],
            "current_q_idx": r2_state["current_q_idx"],
            "answer_count": len(r2_state["player_answers"]),
        },
        "player_count": len(db.data["players"]),
        "leaderboard": db.get_leaderboard(),
    }


def get_r1_vote_counts():
    counts = {"artem": 0, "katya": 0, "both": 0}
    for v in r1_state["votes"].values():
        if v in counts:
            counts[v] += 1
    return counts


def all_player_tg_ids():
    return list(db.data["players"].keys())


def fuzzy_match(user_answer: str, accepted: list) -> bool:
    user_lower = user_answer.lower().strip()
    for ans in accepted:
        if fuzz:
            if fuzz.ratio(user_lower, ans.lower()) >= 75:
                return True
        else:
            if user_lower == ans.lower():
                return True
    return False


# --- BOT ---

if bot:
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        tg_id = str(message.from_user.id)
        if tg_id in db.data["players"]:
            name = db.data["players"][tg_id]["name"]
            await message.answer(f"Привет, {name}! Ты уже в игре 🎉\nОтправь /rename чтобы сменить имя.")
            return
        awaiting_name[tg_id] = True
        await message.answer("Привет! Введи своё имя для игры:")

    @dp.message(Command("rename"))
    async def cmd_rename(message: types.Message):
        tg_id = str(message.from_user.id)
        awaiting_name[tg_id] = True
        await message.answer("Введи новое имя:")

    @dp.callback_query(F.data.startswith("vote_"))
    async def handle_vote(callback: types.CallbackQuery):
        if r1_state["status"] != "voting":
            await callback.answer("Голосование закрыто", show_alert=True)
            return
        choice = callback.data.split("_", 1)[1]
        user_id = str(callback.from_user.id)
        if user_id not in db.data["players"]:
            await callback.answer("Сначала зарегистрируйся: /start", show_alert=True)
            return
        r1_state["votes"][user_id] = choice
        await sio.emit("vote_update", get_r1_vote_counts())
        labels = {"artem": "Артём", "katya": "Катя", "both": "Вдвоём"}
        await callback.answer(f"Голос: {labels.get(choice, choice)}")

    @dp.message(F.text)
    async def handle_text(message: types.Message):
        tg_id = str(message.from_user.id)
        text = message.text.strip()

        if tg_id in awaiting_name:
            del awaiting_name[tg_id]
            if tg_id not in db.data["players"]:
                db.data["players"][tg_id] = {"name": text, "score_r1": 0, "score_r2": 0}
            else:
                db.data["players"][tg_id]["name"] = text
            db.save()
            await sio.emit("player_count_update", {"count": len(db.data["players"])})
            await message.answer(f"Имя сохранено: {text} 🎉")
            return

        if r2_state["status"] == "collecting":
            if tg_id not in db.data["players"]:
                await message.answer("Сначала зарегистрируйся: /start")
                return
            r2_state["player_answers"][tg_id] = text
            count = len(r2_state["player_answers"])
            await sio.emit("answer_received", {"count": count})
            await message.answer("✅ Ответ принят!")


# --- API: STATE & PLAYERS ---

@app.get("/api/state")
async def get_state():
    return build_full_state()

@app.get("/api/players")
async def get_players():
    return db.get_leaderboard()

@app.delete("/api/players/{tg_id}")
async def delete_player(tg_id: str):
    if tg_id in db.data["players"]:
        del db.data["players"][tg_id]
        db.save()
    return {"ok": True}

@app.post("/api/leaderboard")
async def emit_leaderboard():
    await sio.emit("leaderboard_show", {"players": db.get_leaderboard()})
    return {"ok": True}

@app.post("/api/hard_reset")
async def hard_reset():
    for p in db.data["players"].values():
        p["score_r1"] = 0
        p["score_r2"] = 0
    db.save()
    r1_state.update({"current_photo": None, "votes": {}, "status": "idle"})
    r2_state.update({"current_q_idx": None, "player_answers": {}, "status": "idle"})
    await sio.emit("hard_reset", {})
    return {"ok": True}

@app.post("/api/reset_scores/{round_name}")
async def reset_round_scores(round_name: str):
    if round_name not in ("r1", "r2"):
        return {"error": "Invalid round"}
    key = "score_r1" if round_name == "r1" else "score_r2"
    for p in db.data["players"].values():
        p[key] = 0
    db.save()
    return {"ok": True}


# --- API: ROUND 1 ---

@app.get("/api/r1/photos")
async def get_r1_photos():
    return db.data["round1"]["photos"]

@app.post("/api/r1/show/{n}")
async def r1_show(n: int):
    if n < 1 or n > 10:
        return {"error": "Invalid photo number"}
    r1_state["current_photo"] = n
    r1_state["status"] = "showing"
    r1_state["votes"] = {}
    await sio.emit("show_photo", {"n": n, "url": f"/r1img/{n}.png"})
    return {"ok": True}

@app.post("/api/r1/start_voting")
async def r1_start_voting():
    if r1_state["current_photo"] is None:
        return {"error": "No photo selected"}
    r1_state["status"] = "voting"
    r1_state["votes"] = {}
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🧑 Артём", callback_data="vote_artem"),
        InlineKeyboardButton(text="👩 Катя", callback_data="vote_katya"),
        InlineKeyboardButton(text="👫 Вдвоём", callback_data="vote_both"),
    ]])
    sent = 0
    if bot:
        for tg_id in all_player_tg_ids():
            try:
                await bot.send_message(int(tg_id), "Кто это на фото? 🤔", reply_markup=kb)
                sent += 1
            except Exception as e:
                print(f"Send failed {tg_id}: {e}")
    await sio.emit("voting_open", {
        "n": r1_state["current_photo"],
        "vote_counts": get_r1_vote_counts()
    })
    return {"ok": True, "sent": sent}

@app.post("/api/r1/reveal")
async def r1_reveal():
    if r1_state["current_photo"] is None:
        return {"error": "No photo selected"}
    n = str(r1_state["current_photo"])
    correct = db.data["round1"]["photos"].get(n, {}).get("correct", "artem")
    labels = {"artem": "Артём", "katya": "Катя", "both": "Вдвоём"}
    results = []
    for tg_id, vote in r1_state["votes"].items():
        player = db.data["players"].get(tg_id)
        if not player:
            continue
        is_correct = vote == correct
        if is_correct:
            player["score_r1"] = player.get("score_r1", 0) + 1
        results.append({"name": player["name"], "vote": vote, "vote_label": labels.get(vote, vote), "correct": is_correct})
    db.save()
    r1_state["status"] = "revealed"
    await sio.emit("photo_revealed", {
        "n": int(n),
        "full_url": f"/r1img/{n}_{n}.png",
        "correct": correct,
        "correct_label": labels.get(correct, correct),
        "vote_counts": get_r1_vote_counts(),
        "results": results,
        "leaderboard": db.get_leaderboard()
    })
    return {"ok": True}

@app.post("/api/r1/reset")
async def r1_reset():
    r1_state.update({"status": "idle", "current_photo": None, "votes": {}})
    await sio.emit("r1_reset", {})
    return {"ok": True}


class SetR1Answer(BaseModel):
    photo_n: int
    answer: str


@app.post("/api/r1/set_answer")
async def r1_set_answer(body: SetR1Answer):
    n = str(body.photo_n)
    if n not in db.data["round1"]["photos"]:
        return {"error": "Invalid photo"}
    if body.answer not in ("artem", "katya", "both"):
        return {"error": "Must be artem/katya/both"}
    db.data["round1"]["photos"][n]["correct"] = body.answer
    db.save()
    return {"ok": True}


# --- API: ROUND 2 ---

@app.get("/api/r2/questions")
async def get_r2_questions():
    return db.data["round2"]["questions"]

@app.post("/api/r2/show/{idx}")
async def r2_show(idx: int):
    questions = db.data["round2"]["questions"]
    if idx < 0 or idx >= len(questions):
        return {"error": "Invalid question index"}
    r2_state["current_q_idx"] = idx
    r2_state["status"] = "showing"
    r2_state["player_answers"] = {}
    q = questions[idx]
    reader_name = None
    if q.get("reader_tg_id"):
        rid = str(q["reader_tg_id"])
        if rid in db.data["players"]:
            reader_name = db.data["players"][rid]["name"]
    await sio.emit("show_question", {
        "idx": idx,
        "q_num": idx + 1,
        "reader_name": reader_name
    })
    return {"ok": True}

@app.post("/api/r2/send_to_reader")
async def r2_send_to_reader():
    if r2_state["current_q_idx"] is None:
        return {"error": "No question selected"}
    q = db.data["round2"]["questions"][r2_state["current_q_idx"]]
    reader_tg_id = q.get("reader_tg_id")
    if not reader_tg_id:
        return {"error": "No reader assigned for this question"}
    r2_state["status"] = "reading"
    await sio.emit("reading_started", {"idx": r2_state["current_q_idx"]})
    if bot:
        try:
            await bot.send_message(
                int(reader_tg_id),
                f"📖 *Твой текст для чтения:*\n\n{q['text']}",
                parse_mode="Markdown"
            )
        except Exception as e:
            return {"error": str(e)}
    return {"ok": True}

@app.post("/api/r2/open_answers")
async def r2_open_answers():
    if r2_state["current_q_idx"] is None:
        return {"error": "No question selected"}
    r2_state["status"] = "collecting"
    r2_state["player_answers"] = {}
    await sio.emit("answers_open", {"idx": r2_state["current_q_idx"]})
    if bot:
        for tg_id in all_player_tg_ids():
            try:
                await bot.send_message(int(tg_id), "💬 Напиши свой ответ одним словом:")
            except:
                pass
    return {"ok": True}

@app.post("/api/r2/close_answers")
async def r2_close_answers():
    if r2_state["current_q_idx"] is None:
        return {"error": "No question selected"}
    q = db.data["round2"]["questions"][r2_state["current_q_idx"]]
    accepted = q.get("accepted", [])
    results = []
    for tg_id, answer in r2_state["player_answers"].items():
        player = db.data["players"].get(tg_id)
        if not player:
            continue
        is_correct = fuzzy_match(answer, accepted)
        if is_correct:
            player["score_r2"] = player.get("score_r2", 0) + 1
        results.append({"name": player["name"], "answer": answer, "correct": is_correct})
    db.save()
    r2_state["status"] = "revealed"
    await sio.emit("question_result", {
        "idx": r2_state["current_q_idx"],
        "accepted": accepted,
        "results": results,
        "leaderboard": db.get_leaderboard()
    })
    if bot:
        for tg_id, answer in r2_state["player_answers"].items():
            try:
                r = next((x for x in results if x["answer"] == answer), None)
                if r:
                    icon = "✅" if r["correct"] else "❌"
                    await bot.send_message(
                        int(tg_id),
                        f"{icon} Твой ответ: «{answer}»\nПравильный ответ: {', '.join(accepted)}"
                    )
            except:
                pass
    return {"ok": True}

@app.post("/api/r2/reset")
async def r2_reset():
    r2_state.update({"status": "idle", "current_q_idx": None, "player_answers": {}})
    await sio.emit("r2_reset", {})
    return {"ok": True}


class UpdateQuestion(BaseModel):
    idx: int
    accepted: Optional[List[str]] = None
    text: Optional[str] = None
    reader_tg_id: Optional[int] = None
    set_reader: bool = False


class ReorderQuestions(BaseModel):
    order: List[int]


@app.post("/api/r2/update_question")
async def r2_update_question(body: UpdateQuestion):
    questions = db.data["round2"]["questions"]
    if body.idx < 0 or body.idx >= len(questions):
        return {"error": "Invalid index"}
    if body.accepted is not None:
        questions[body.idx]["accepted"] = body.accepted
    if body.text is not None:
        questions[body.idx]["text"] = body.text
    if body.set_reader:
        questions[body.idx]["reader_tg_id"] = body.reader_tg_id
    db.save()
    return {"ok": True}


@app.post("/api/r2/reorder")
async def r2_reorder(body: ReorderQuestions):
    questions = db.data["round2"]["questions"]
    id_to_q = {q["id"]: q for q in questions}
    if set(body.order) != set(id_to_q.keys()):
        return {"error": "Invalid question IDs"}
    db.data["round2"]["questions"] = [id_to_q[qid] for qid in body.order]
    db.save()
    return {"ok": True}


# --- SERVE HTML ---

app.mount("/socket.io", socket_app)

@app.get("/qr.jpg")
async def serve_qr():
    if os.path.exists("qr.jpg"):
        return FileResponse("qr.jpg", media_type="image/jpeg")
    return {"error": "QR not found"}


@app.get("/")
async def index():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/admin")
async def admin():
    with open("admin.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.on_event("startup")
async def on_startup():
    if bot:
        asyncio.create_task(dp.start_polling(bot))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
