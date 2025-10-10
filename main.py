from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json
import jwt
import hashlib
import uuid
import random
import requests
from pathlib import Path

app = FastAPI(title="Quiz System API")
security = HTTPBearer()

# Konfiguratsiya
SECRET_KEY = "your-secret-key-change-this"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 999999

# Telegram Bot Token - backendda saqlanadi
TELEGRAM_BOT_TOKEN = "8157743798:AAELzxyyFLSMxbT-XL4l-3ZVmxVBXYOY0Ro"
TELEGRAM_USER_ID = 1066137436

# Database files
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"
CATEGORIES_FILE = DATA_DIR / "categories.json"
QUESTIONS_FILE = DATA_DIR / "questions.json"
RESULTS_FILE = DATA_DIR / "results.json"

# Initialize JSON files
def init_db():
    if not USERS_FILE.exists():
        initial_data = {
            "users": [{
                "id": "super_admin_001",
                "username": "superadmin",
                "password": hashlib.sha256("admin123".encode()).hexdigest(),
                "role": "super_admin",
                "created_at": datetime.now().isoformat()
            }]
        }
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(initial_data, f, ensure_ascii=False, indent=2)
    
    if not CATEGORIES_FILE.exists():
        with open(CATEGORIES_FILE, 'w', encoding='utf-8') as f:
            json.dump({"categories": []}, f, ensure_ascii=False, indent=2)
    
    if not QUESTIONS_FILE.exists():
        with open(QUESTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"questions": []}, f, ensure_ascii=False, indent=2)
    
    if not RESULTS_FILE.exists():
        with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"results": []}, f, ensure_ascii=False, indent=2)

init_db()

# Models
class UserCreate(BaseModel):
    username: str
    password: str
    role: str

class UserLogin(BaseModel):
    username: str
    password: str

class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    icon: Optional[str] = "📚"
    allowedRoles: List[str]  # ["povar", "ofitsiant"]

class Question(BaseModel):
    question: str
    options: List[str]
    correctAnswer: str  # To'g'ri javobning o'zi (text)

class QuestionCreate(BaseModel):
    categoryId: str
    questions: List[Question]

class QuestionSingle(BaseModel):
    categoryId: str
    question: str
    options: List[str]
    correctAnswer: str  # To'g'ri javobning o'zi (text)

class Answer(BaseModel):
    questionId: str
    answer: Any  # int yoki string bo'lishi mumkin

class QuizSubmit(BaseModel):
    categoryId: str
    answers: List[Answer]
    timeSpent: int  # seconds

class Token(BaseModel):
    access_token: str
    token_type: str

# Helper functions
def load_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_user_by_username(username: str):
    data = load_json(USERS_FILE)
    for user in data["users"]:
        if user["username"] == username:
            return user
    return None

def shuffle_questions(questions: List[dict], user_id: str, category_id: str):
    """Har bir user uchun savollar va javoblarni aralashtirib beradi"""
    seed = hashlib.md5(f"{user_id}{category_id}{datetime.now().date()}".encode()).hexdigest()
    random.seed(seed)
    
    shuffled = []
    for q in questions:
        new_q = q.copy()
        
        # Javoblarni aralashtiramiz
        options = q["options"].copy()
        random.shuffle(options)
        
        new_q["options"] = options
        # correctAnswer o'zi text bo'lgani uchun o'zgartirish kerak emas
        shuffled.append(new_q)
    
    # Savollar tartibini ham aralashtiramiz
    random.shuffle(shuffled)
    return shuffled

def send_telegram_message(bot_token: str, user_id: int, message: str):
    """Telegram bot orqali xabar yuborish"""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            "chat_id": user_id,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=data)
        return response.json()
    except Exception as e:
        print(f"Telegram message error: {e}")
        return None

def check_category_access(category: dict, user_role: str) -> bool:
    """User kategoriyaga kirish huquqini tekshirish"""
    if user_role == "super_admin":
        return True
    return user_role in category.get("allowedRoles", [])

# API Endpoints
@app.post("/api/register", response_model=Token)
async def register(user: UserCreate):
    """Har qanday foydalanuvchi ro'yxatdan o'tishi mumkin"""

    data = load_json(USERS_FILE)

    # Username mavjudligini tekshirish
    if get_user_by_username(user.username):
        raise HTTPException(status_code=400, detail="Username already exists")

    # Yangi foydalanuvchini yaratish
    new_user = {
        "id": str(uuid.uuid4()),
        "username": user.username,
        "password": hashlib.sha256(user.password.encode()).hexdigest(),
        "role": user.role,
        "created_at": datetime.now().isoformat()
    }

    data["users"].append(new_user)
    save_json(USERS_FILE, data)

    access_token = create_access_token({"sub": user.username, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/login", response_model=Token)
async def login(user: UserLogin):
    """Login qilish"""
    db_user = get_user_by_username(user.username)
    
    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    hashed_password = hashlib.sha256(user.password.encode()).hexdigest()
    if db_user["password"] != hashed_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token({
        "sub": user.username, 
        "role": db_user["role"],
        "user_id": db_user["id"]
    })
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "role":db_user["role"],
        "user": {
            "username": db_user["username"],
            "role": db_user["role"],
            "id": db_user["id"]
        }
    }

@app.get("/api/roles")
async def get_roles(current_user: dict = Depends(verify_token)):
    """Barcha rollarni olish (kategoriya yaratishda kerak)"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can view roles")
    
    data = load_json(USERS_FILE)
    roles = list(set([u["role"] for u in data["users"] if u["role"] != "super_admin"]))
    return {"roles": roles}

# KATEGORIYA ENDPOINTS

@app.post("/api/categories")
async def create_category(category: CategoryCreate, current_user: dict = Depends(verify_token)):
    """Kategoriya yaratish (super admin)"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can create categories")
    
    data = load_json(CATEGORIES_FILE)
    
    new_category = {
        "id": str(uuid.uuid4()),
        "name": category.name,
        "description": category.description,
        "icon": category.icon,
        "allowedRoles": category.allowedRoles,
        "questionCount": 0,
        "created_at": datetime.now().isoformat()
    }
    
    data["categories"].append(new_category)
    save_json(CATEGORIES_FILE, data)
    
    return {
        "message": "Kategoriya yaratildi",
        "category": new_category,
        "success": True
    }

@app.get("/api/categories")
async def get_categories(current_user: dict = Depends(verify_token)):
    """Userga ruxsat berilgan kategoriyalarni olish (user rolega asoslanib)"""
    data = load_json(CATEGORIES_FILE)
    user_role = current_user.get("role")
    
    # Super admin barcha kategoriyalarni ko'radi
    if user_role == "super_admin":
        categories = data["categories"]
    else:
        # Oddiy user faqat o'z roliga ruxsat berilgan kategoriyalarni ko'radi
        categories = [
            cat for cat in data["categories"]
            if user_role in cat.get("allowedRoles", [])
        ]
    
    # Har bir kategoriya uchun savol sonini hisoblash
    questions_data = load_json(QUESTIONS_FILE)
    for cat in categories:
        cat["questionCount"] = len([
            q for q in questions_data["questions"]
            if q["categoryId"] == cat["id"]
        ])
    
    return {
        "categories": categories, 
        "total": len(categories),
        "userRole": user_role
    }

@app.get("/api/categories/{category_id}")
async def get_category_detail(category_id: str, current_user: dict = Depends(verify_token)):
    """Kategoriya tafsilotlari"""
    data = load_json(CATEGORIES_FILE)
    category = next((c for c in data["categories"] if c["id"] == category_id), None)
    
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    # Ruxsatni tekshirish
    if not check_category_access(category, current_user.get("role")):
        raise HTTPException(status_code=403, detail="Bu kategoriyaga ruxsatingiz yo'q")
    
    # Savol sonini qo'shish
    questions_data = load_json(QUESTIONS_FILE)
    category["questionCount"] = len([
        q for q in questions_data["questions"]
        if q["categoryId"] == category_id
    ])
    
    return {"category": category}

@app.put("/api/categories/{category_id}")
async def update_category(category_id: str, category: CategoryCreate, current_user: dict = Depends(verify_token)):
    """Kategoriyani yangilash"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can update categories")
    
    data = load_json(CATEGORIES_FILE)
    cat_index = next((i for i, c in enumerate(data["categories"]) if c["id"] == category_id), None)
    
    if cat_index is None:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    data["categories"][cat_index].update({
        "name": category.name,
        "description": category.description,
        "icon": category.icon,
        "allowedRoles": category.allowedRoles,
        "updated_at": datetime.now().isoformat()
    })
    
    save_json(CATEGORIES_FILE, data)
    return {"message": "Kategoriya yangilandi", "success": True}

@app.delete("/api/categories/{category_id}")
async def delete_category(category_id: str, current_user: dict = Depends(verify_token)):
    """Kategoriyani o'chirish"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can delete categories")
    
    data = load_json(CATEGORIES_FILE)
    data["categories"] = [c for c in data["categories"] if c["id"] != category_id]
    save_json(CATEGORIES_FILE, data)
    
    # Kategoriyaga tegishli savollarni ham o'chirish
    questions_data = load_json(QUESTIONS_FILE)
    questions_data["questions"] = [q for q in questions_data["questions"] if q["categoryId"] != category_id]
    save_json(QUESTIONS_FILE, questions_data)
    
    return {"message": "Kategoriya o'chirildi", "success": True}

# SAVOL ENDPOINTS

@app.post("/api/questions")
async def create_questions(questions_data: QuestionCreate, current_user: dict = Depends(verify_token)):
    """Savollar yaratish (list) - kategoriya bilan"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can create questions")
    
    # Kategoriya mavjudligini tekshirish
    categories = load_json(CATEGORIES_FILE)
    category = next((c for c in categories["categories"] if c["id"] == questions_data.categoryId), None)
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    data = load_json(QUESTIONS_FILE)
    
    for q in questions_data.questions:
        # To'g'ri javob options ichida borligini tekshirish
        if q.correctAnswer not in q.options:
            raise HTTPException(
                status_code=400, 
                detail=f"To'g'ri javob '{q.correctAnswer}' options ichida topilmadi"
            )
        
        new_question = {
            "id": str(uuid.uuid4()),
            "categoryId": questions_data.categoryId,
            "question": q.question,
            "options": q.options,
            "correctAnswer": q.correctAnswer,  # Text sifatida
            "created_at": datetime.now().isoformat()
        }
        data["questions"].append(new_question)
    
    save_json(QUESTIONS_FILE, data)
    return {
        "message": f"{len(questions_data.questions)} ta savol qo'shildi",
        "categoryId": questions_data.categoryId,
        "success": True
    }

@app.post("/api/questions/single")
async def create_single_question(question: QuestionSingle, current_user: dict = Depends(verify_token)):
    """Bitta savol qo'shish - kategoriya bilan"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can create questions")
    
    # Kategoriya mavjudligini tekshirish
    categories = load_json(CATEGORIES_FILE)
    category = next((c for c in categories["categories"] if c["id"] == question.categoryId), None)
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    # To'g'ri javob options ichida borligini tekshirish
    if question.correctAnswer not in question.options:
        raise HTTPException(
            status_code=400, 
            detail=f"To'g'ri javob '{question.correctAnswer}' options ichida topilmadi"
        )
    
    data = load_json(QUESTIONS_FILE)
    
    new_question = {
        "id": str(uuid.uuid4()),
        "categoryId": question.categoryId,
        "question": question.question,
        "options": question.options,
        "correctAnswer": question.correctAnswer,  # Text sifatida
        "created_at": datetime.now().isoformat()
    }
    data["questions"].append(new_question)
    save_json(QUESTIONS_FILE, data)
    
    return {
        "message": "Savol qo'shildi",
        "questionId": new_question["id"],
        "categoryId": question.categoryId,
        "success": True
    }

@app.get("/api/categories/{category_id}/questions")
async def get_category_questions(category_id: str, current_user: dict = Depends(verify_token)):
    """Kategoriya bo'yicha savollarni olish (user rolega qarab)"""
    # Kategoriyani topish
    categories = load_json(CATEGORIES_FILE)
    category = next((c for c in categories["categories"] if c["id"] == category_id), None)
    
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    user_role = current_user.get("role")
    
    # Super admin emas bo'lsa, ruxsatni tekshirish
    if user_role != "super_admin":
        if user_role not in category.get("allowedRoles", []):
            raise HTTPException(
                status_code=403, 
                detail=f"Bu kategoriya faqat {', '.join(category.get('allowedRoles', []))} rollari uchun"
            )
    
    # Savollarni olish
    data = load_json(QUESTIONS_FILE)
    questions = [q for q in data["questions"] if q["categoryId"] == category_id]
    
    if not questions:
        return {
            "questions": [], 
            "total": 0, 
            "categoryName": category["name"],
            "userRole": user_role
        }
    
    # User uchun savollarni aralashtiramiz
    shuffled = shuffle_questions(questions, current_user["sub"], category_id)
    
    # Javoblarni yashiramiz (frontend uchun)
    response_questions = []
    for q in shuffled:
        response_questions.append({
            "id": q["id"],
            "question": q["question"],
            "options": q["options"]
        })
    
    return {
        "questions": response_questions,
        "total": len(response_questions),
        "categoryId": category_id,
        "categoryName": category["name"],
        "userRole": user_role
    }

@app.post("/api/check")
async def check_answers(submission: QuizSubmit, current_user: dict = Depends(verify_token)):
    """Javoblarni tekshirish va natijani Telegramga yuborish (bot token backendda)"""
    # Kategoriya tekshirish
    categories = load_json(CATEGORIES_FILE)
    category = next((c for c in categories["categories"] if c["id"] == submission.categoryId), None)
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    # User ruxsatini tekshirish
    user_role = current_user.get("role")
    if user_role != "super_admin":
        if user_role not in category.get("allowedRoles", []):
            raise HTTPException(status_code=403, detail="Bu kategoriyaga ruxsatingiz yo'q")
    
    data = load_json(QUESTIONS_FILE)
    all_questions = {q["id"]: q for q in data["questions"] if q["categoryId"] == submission.categoryId}
    
    # Natijalarni hisoblash
    total_questions = len(submission.answers)
    correct_count = 0
    wrong_answers = []
    
    for answer in submission.answers:
        question = all_questions.get(answer.questionId)
        if not question:
            continue
        
        user_answer = answer.answer
        correct_answer = question["correctAnswer"]
        
        # Javob int yoki string bo'lishi mumkin
        if isinstance(user_answer, int):
            # Index bo'lsa, textga o'tkazamiz
            if 0 <= user_answer < len(question["options"]):
                user_answer_text = question["options"][user_answer]
            else:
                user_answer_text = "Noma'lum"
        else:
            user_answer_text = user_answer
        
        # Textlarni solishtirish (kichik-katta harflarni hisobga olmasdan)
        is_correct = user_answer_text.strip().lower() == correct_answer.strip().lower()
        
        if is_correct:
            correct_count += 1
        else:
            wrong_answers.append({
                "question": question["question"],
                "userAnswer": user_answer_text,
                "correctAnswer": correct_answer
            })
    
    # Natijani saqlash
    result = {
        "id": str(uuid.uuid4()),
        "username": current_user["sub"],
        "userRole": user_role,
        "categoryId": submission.categoryId,
        "categoryName": category["name"],
        "totalQuestions": total_questions,
        "correctAnswers": correct_count,
        "wrongAnswers": len(wrong_answers),
        "timeSpent": submission.timeSpent,
        "percentage": round((correct_count / total_questions) * 100, 2) if total_questions > 0 else 0,
        "details": wrong_answers,
        "submittedAt": datetime.now().isoformat()
    }
    
    results_data = load_json(RESULTS_FILE)
    results_data["results"].append(result)
    save_json(RESULTS_FILE, results_data)
    
    # Telegram xabari
    minutes = submission.timeSpent // 60
    seconds = submission.timeSpent % 60
    
    message = f"""
📊 <b>Test Natijalari</b>

📚 Kategoriya: {category['name']}
👤 Foydalanuvchi: {current_user['sub']}
🎭 Rol: {user_role}
✅ To'g'ri javoblar: {correct_count}/{total_questions}
❌ Xato javoblar: {len(wrong_answers)}
📈 Foiz: {result['percentage']}%
⏱ Vaqt: {minutes} daqiqa {seconds} soniya
📅 Sana: {datetime.now().strftime('%Y-%m-%d %H:%M')}

"""
    
    if wrong_answers:
        message += "\n<b>Xato javoblar:</b>\n"
        for i, wa in enumerate(wrong_answers[:10], 1):  # Faqat 10 ta xatoni ko'rsatamiz
            message += f"\n{i}. {wa['question'][:100]}...\n"
            message += f"   ❌ Siz: {wa['userAnswer']}\n"
            message += f"   ✅ To'g'ri: {wa['correctAnswer']}\n"
        
        if len(wrong_answers) > 10:
            message += f"\n... va yana {len(wrong_answers) - 10} ta xato"
    else:
        message += "\n🎉 <b>Tabriklaymiz! Barcha javoblar to'g'ri!</b>"
    
    # Telegramga yuborish (backend tokendan foydalanib)
    send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID, message)
    
    return {
        "success": True,
        "result": {
            "totalQuestions": total_questions,
            "correctAnswers": correct_count,
            "wrongAnswers": len(wrong_answers),
            "percentage": result['percentage'],
            "timeSpent": submission.timeSpent,
            "categoryName": category['name']
        },
        "message": "Natijalar Telegramga yuborildi"
    }

@app.get("/api/results")
async def get_results(current_user: dict = Depends(verify_token)):
    """Barcha natijalarni ko'rish"""
    data = load_json(RESULTS_FILE)
    
    if current_user.get("role") == "super_admin":
        # Super admin barcha natijalarni ko'radi
        return {"results": data["results"]}
    else:
        # Oddiy user faqat o'z natijalarini ko'radi
        user_results = [r for r in data["results"] if r["username"] == current_user["sub"]]
        return {"results": user_results}

@app.get("/api/results/category/{category_id}")
async def get_category_results(category_id: str, current_user: dict = Depends(verify_token)):
    """Kategoriya bo'yicha natijalarni ko'rish"""
    data = load_json(RESULTS_FILE)
    
    if current_user.get("role") == "super_admin":
        results = [r for r in data["results"] if r["categoryId"] == category_id]
    else:
        results = [
            r for r in data["results"]
            if r["categoryId"] == category_id and r["username"] == current_user["sub"]
        ]
    
    return {"results": results, "categoryId": category_id}

@app.get("/")
async def root():
    return {
        "message": "Quiz System API with Categories",
        "version": "2.0",
        "endpoints": {
            "POST /api/login": "Login qilish",
            "POST /api/register": "Yangi user yaratish (super admin)",
            "GET /api/roles": "Rollarni olish",
            "POST /api/categories": "Kategoriya yaratish",
            "GET /api/categories": "Kategoriyalarni olish",
            "GET /api/categories/{id}": "Kategoriya tafsilotlari",
            "PUT /api/categories/{id}": "Kategoriyani yangilash",
            "DELETE /api/categories/{id}": "Kategoriyani o'chirish",
            "POST /api/questions": "Savollar qo'shish (list)",
            "POST /api/questions/single": "Bitta savol qo'shish",
            "GET /api/categories/{id}/questions": "Kategoriya savollarini olish",
            "POST /api/check": "Javoblarni tekshirish",
            "GET /api/results": "Natijalarni ko'rish",
            "GET /api/results/category/{id}": "Kategoriya natijalarini ko'rish"
        }
    }#e4126d65-cad3-4577-a3ee-c3de134ada89

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8050)