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

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = "8157743798:AAELzxyyFLSMxbT-XL4l-3ZVmxVBXYOY0Ro"
TELEGRAM_USER_ID = 1066137436

# Database files
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"
CATEGORIES_FILE = DATA_DIR / "categories.json"
QUESTIONS_FILE = DATA_DIR / "questions.json"
RESULTS_FILE = DATA_DIR / "results.json"
STATISTICS_FILE = DATA_DIR / "statistics.json"

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
    
    if not STATISTICS_FILE.exists():
        with open(STATISTICS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"statistics": {}}, f, ensure_ascii=False, indent=2)

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
    allowedRoles: List[str]

class Question(BaseModel):
    question: str
    options: List[str]
    correctAnswer: str

class QuestionCreate(BaseModel):
    categoryId: str
    questions: List[Question]

class QuestionSingle(BaseModel):
    categoryId: str
    question: str
    options: List[str]
    correctAnswer: str

class Answer(BaseModel):
    questionId: str
    answer: Any

class QuizSubmit(BaseModel):
    categoryId: str
    answers: List[Answer]
    timeSpent: int

class ResultSubmit(BaseModel):
    categoryId: str
    totalQuestions: int
    correctAnswers: int
    wrongAnswers: int
    percentage: float
    timeSpent: int
    categoryName: str
    wrongDetails: Optional[List[Dict]] = []

class Token(BaseModel):
    access_token: str
    token_type: str
    user: Optional[Dict[str, Any]] 


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
    seed = hashlib.md5(f"{user_id}{category_id}{datetime.now().date()}".encode()).hexdigest()
    random.seed(seed)
    
    shuffled = []
    for q in questions:
        new_q = q.copy()
        options = q["options"].copy()
        random.shuffle(options)
        new_q["options"] = options
        shuffled.append(new_q)
    
    random.shuffle(shuffled)
    return shuffled

def send_telegram_message(bot_token: str, user_id: int, message: str):
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
    if user_role == "super_admin":
        return True
    return user_role in category.get("allowedRoles", [])

def update_statistics(username: str, category_id: str, category_name: str, result_data: dict):
    """Statistikani yangilash - barcha testlar hisobini saqlash"""
    stats_data = load_json(STATISTICS_FILE)
    
    if category_id not in stats_data["statistics"]:
        stats_data["statistics"][category_id] = {
            "categoryName": category_name,
            "users": {}
        }
    
    # Agar user mavjud bo'lsa, qo'shib borish
    if username in stats_data["statistics"][category_id]["users"]:
        existing = stats_data["statistics"][category_id]["users"][username]
        
        # Umumiy ma'lumotlarni yangilash
        total_correct = existing["totalCorrectAnswers"] + result_data["correctAnswers"]
        total_questions = existing["totalQuestions"] + result_data["totalQuestions"]
        test_count = existing["testCount"] + 1
        
        stats_data["statistics"][category_id]["users"][username] = {
            "username": username,
            "totalCorrectAnswers": total_correct,
            "totalQuestions": total_questions,
            "testCount": test_count,
            "averagePercentage": round((total_correct / total_questions) * 100, 2) if total_questions > 0 else 0,
            "lastUpdated": datetime.now().isoformat()
        }
    else:
        # Yangi user uchun
        stats_data["statistics"][category_id]["users"][username] = {
            "username": username,
            "totalCorrectAnswers": result_data["correctAnswers"],
            "totalQuestions": result_data["totalQuestions"],
            "testCount": 1,
            "averagePercentage": result_data["percentage"],
            "lastUpdated": datetime.now().isoformat()
        }
    
    save_json(STATISTICS_FILE, stats_data)

# API Endpoints
@app.post("/api/register", response_model=Token)
async def register(user: UserCreate):
    data = load_json(USERS_FILE)

    if get_user_by_username(user.username):
        raise HTTPException(status_code=400, detail="Username already exists")

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
        "role": db_user["role"],
        "user": {
            "username": db_user["username"],
            "role": db_user["role"],
            "id": db_user["id"]
        }
    }

@app.get("/api/roles")
async def get_roles(current_user: dict = Depends(verify_token)):
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can view roles")
    
    data = load_json(USERS_FILE)
    roles = list(set([u["role"] for u in data["users"] if u["role"] != "super_admin"]))
    return {"roles": roles}

@app.post("/api/categories")
async def create_category(category: CategoryCreate, current_user: dict = Depends(verify_token)):
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
    data = load_json(CATEGORIES_FILE)
    user_role = current_user.get("role")
    
    if user_role == "super_admin":
        categories = data["categories"]
    else:
        categories = [
            cat for cat in data["categories"]
            if user_role in cat.get("allowedRoles", [])
        ]
    
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
    data = load_json(CATEGORIES_FILE)
    category = next((c for c in data["categories"] if c["id"] == category_id), None)
    
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    if not check_category_access(category, current_user.get("role")):
        raise HTTPException(status_code=403, detail="Bu kategoriyaga ruxsatingiz yo'q")
    
    questions_data = load_json(QUESTIONS_FILE)
    category["questionCount"] = len([
        q for q in questions_data["questions"]
        if q["categoryId"] == category_id
    ])
    
    return {"category": category}

@app.put("/api/categories/{category_id}")
async def update_category(category_id: str, category: CategoryCreate, current_user: dict = Depends(verify_token)):
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
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can delete categories")
    
    data = load_json(CATEGORIES_FILE)
    data["categories"] = [c for c in data["categories"] if c["id"] != category_id]
    save_json(CATEGORIES_FILE, data)
    
    questions_data = load_json(QUESTIONS_FILE)
    questions_data["questions"] = [q for q in questions_data["questions"] if q["categoryId"] != category_id]
    save_json(QUESTIONS_FILE, questions_data)
    
    return {"message": "Kategoriya o'chirildi", "success": True}

@app.post("/api/questions")
async def create_questions(questions_data: QuestionCreate, current_user: dict = Depends(verify_token)):
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can create questions")
    
    categories = load_json(CATEGORIES_FILE)
    category = next((c for c in categories["categories"] if c["id"] == questions_data.categoryId), None)
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    data = load_json(QUESTIONS_FILE)
    
    for q in questions_data.questions:
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
            "correctAnswer": q.correctAnswer,
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
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can create questions")
    
    categories = load_json(CATEGORIES_FILE)
    category = next((c for c in categories["categories"] if c["id"] == question.categoryId), None)
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
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
        "correctAnswer": question.correctAnswer,
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
# Savolni yangilash
@app.put("/api/questions/{question_id}")
async def update_question(question_id: str, question: QuestionSingle, current_user: dict = Depends(verify_token)):
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can update questions")
    
    if question.correctAnswer not in question.options:
        raise HTTPException(
            status_code=400, 
            detail=f"To'g'ri javob '{question.correctAnswer}' options ichida topilmadi"
        )
    
    data = load_json(QUESTIONS_FILE)
    
    question_index = next((i for i, q in enumerate(data["questions"]) if q["id"] == question_id), None)
    if question_index is None:
        raise HTTPException(status_code=404, detail="Savol topilmadi")
    
    data["questions"][question_index].update({
        "categoryId": question.categoryId,
        "question": question.question,
        "options": question.options,
        "correctAnswer": question.correctAnswer,
        "updated_at": datetime.now().isoformat()
    })
    
    save_json(QUESTIONS_FILE, data)
    
    return {
        "message": "Savol yangilandi",
        "questionId": question_id,
        "success": True
    }

# Savolni o'chirish
@app.delete("/api/questions/{question_id}")
async def delete_question(question_id: str, current_user: dict = Depends(verify_token)):
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can delete questions")
    
    data = load_json(QUESTIONS_FILE)
    
    initial_count = len(data["questions"])
    data["questions"] = [q for q in data["questions"] if q["id"] != question_id]
    
    if len(data["questions"]) == initial_count:
        raise HTTPException(status_code=404, detail="Savol topilmadi")
    
    save_json(QUESTIONS_FILE, data)
    
    return {
        "message": "Savol o'chirildi",
        "success": True
    }

@app.get("/api/categories/{category_id}/questions")
async def get_category_questions(category_id: str, current_user: dict = Depends(verify_token)):
    categories = load_json(CATEGORIES_FILE)
    category = next((c for c in categories["categories"] if c["id"] == category_id), None)
    
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    user_role = current_user.get("role")
    
    if user_role != "super_admin":
        if user_role not in category.get("allowedRoles", []):
            raise HTTPException(
                status_code=403, 
                detail=f"Bu kategoriya faqat {', '.join(category.get('allowedRoles', []))} rollari uchun"
            )
    
    data = load_json(QUESTIONS_FILE)
    questions = [q for q in data["questions"] if q["categoryId"] == category_id]
    
    if not questions:
        return {
            "questions": [], 
            "total": 0, 
            "categoryName": category["name"],
            "userRole": user_role
        }
    
    shuffled = shuffle_questions(questions, current_user["sub"], category_id)
    
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
    categories = load_json(CATEGORIES_FILE)
    category = next((c for c in categories["categories"] if c["id"] == submission.categoryId), None)
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    user_role = current_user.get("role")
    if user_role != "super_admin":
        if user_role not in category.get("allowedRoles", []):
            raise HTTPException(status_code=403, detail="Bu kategoriyaga ruxsatingiz yo'q")
    
    data = load_json(QUESTIONS_FILE)
    all_questions = {q["id"]: q for q in data["questions"] if q["categoryId"] == submission.categoryId}
    
    total_questions = len(submission.answers)
    correct_count = 0
    wrong_answers = []
    
    for answer in submission.answers:
        question = all_questions.get(answer.questionId)
        if not question:
            continue
        
        user_answer = answer.answer
        correct_answer = question["correctAnswer"]
        
        if isinstance(user_answer, int):
            if 0 <= user_answer < len(question["options"]):
                user_answer_text = question["options"][user_answer]
            else:
                user_answer_text = "Noma'lum"
        else:
            user_answer_text = user_answer
        
        is_correct = user_answer_text.strip().lower() == correct_answer.strip().lower()
        
        if is_correct:
            correct_count += 1
        else:
            wrong_answers.append({
                "question": question["question"],
                "userAnswer": user_answer_text,
                "correctAnswer": correct_answer
            })
    
    percentage = round((correct_count / total_questions) * 100, 2) if total_questions > 0 else 0
    
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
        "percentage": percentage,
        "details": wrong_answers,
        "submittedAt": datetime.now().isoformat()
    }
    
    results_data = load_json(RESULTS_FILE)
    results_data["results"].append(result)
    save_json(RESULTS_FILE, results_data)
    
    return {
        "success": True,
        "result": {
            "categoryId": submission.categoryId,
            "totalQuestions": total_questions,
            "correctAnswers": correct_count,
            "wrongAnswers": len(wrong_answers),
            "percentage": percentage,
            "timeSpent": submission.timeSpent,
            "categoryName": category['name'],
            "wrongDetails": wrong_answers
        },
        "message": "Natija tayyor. Yuborish uchun /api/submit-result endpointiga yuboring"
    }

@app.post("/api/submit-result")
async def submit_result_to_telegram(result_data: ResultSubmit, current_user: dict = Depends(verify_token)):
    update_statistics(
        username=current_user["sub"],
        category_id=result_data.categoryId,
        category_name=result_data.categoryName,
        result_data={
            "correctAnswers": result_data.correctAnswers,
            "totalQuestions": result_data.totalQuestions,
            "percentage": result_data.percentage
        }
    )
    
    minutes = result_data.timeSpent // 60
    seconds = result_data.timeSpent % 60
    
    message = f"""
📊 <b>Test Natijalari</b>

📚 Kategoriya: {result_data.categoryName}
👤 Foydalanuvchi: {current_user['sub']}
🎭 Rol: {current_user.get('role', 'N/A')}
✅ To'g'ri javoblar: {result_data.correctAnswers}/{result_data.totalQuestions}
❌ Xato javoblar: {result_data.wrongAnswers}
📈 Foiz: {result_data.percentage}%
⏱ Vaqt: {minutes} daqiqa {seconds} soniya
📅 Sana: {datetime.now().strftime('%Y-%m-%d %H:%M')}

"""
    
    if result_data.wrongDetails and len(result_data.wrongDetails) > 0:
        message += "\n<b>Xato javoblar:</b>\n"
        for i, wa in enumerate(result_data.wrongDetails[:10], 1):
            message += f"\n{i}. {wa['question'][:100]}...\n"
            message += f"   ❌ Siz: {wa['userAnswer']}\n"
            message += f"   ✅ To'g'ri: {wa['correctAnswer']}\n"
        
        if len(result_data.wrongDetails) > 10:
            message += f"\n... va yana {len(result_data.wrongDetails) - 10} ta xato"
    else:
        message += "\n🎉 <b>Tabriklaymiz! Barcha javoblar to'g'ri!</b>"
    
    telegram_response = send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID, message)
    
    return {
        "success": True,
        "message": "Natijalar Telegramga muvaffaqiyatli yuborildi!",
        "telegram_response": telegram_response
    }

@app.get("/api/statistics")
async def get_all_statistics(current_user: dict = Depends(verify_token)):
    """Barcha kategoriyalar statistikasi - oddiy ko'rinish"""
    categories = load_json(CATEGORIES_FILE)
    user_role = current_user.get("role")
    
    if user_role == "super_admin":
        accessible_categories = categories["categories"]
    else:
        accessible_categories = [
            cat for cat in categories["categories"]
            if user_role in cat.get("allowedRoles", [])
        ]
    
    stats_data = load_json(STATISTICS_FILE)
    all_stats = []
    
    for category in accessible_categories:
        category_id = category["id"]
        
        if category_id in stats_data["statistics"]:
            category_stats = stats_data["statistics"][category_id]
            
            # Oddiy ko'rinish uchun
            simple_stats = []
            for username, data in category_stats["users"].items():
                simple_stats.append({
                    "username": username,
                    "testCount": data["testCount"],
                    "percentage": data["averagePercentage"]
                })
            
            # Foizga ko'ra sortlash
            simple_stats.sort(key=lambda x: x["percentage"], reverse=True)
            
            all_stats.append({
                "categoryId": category_id,
                "categoryName": category["name"],
                "icon": category.get("icon", "📚"),
                "statistics": simple_stats,
                "totalUsers": len(simple_stats)
            })
        else:
            all_stats.append({
                "categoryId": category_id,
                "categoryName": category["name"],
                "icon": category.get("icon", "📚"),
                "statistics": [],
                "totalUsers": 0
            })
    
    return {
        "success": True,
        "totalCategories": len(all_stats),
        "userRole": user_role,
        "statistics": all_stats
    }

@app.get("/api/statistics/{category_id}")
async def get_category_statistics(category_id: str, current_user: dict = Depends(verify_token)):
    """Bitta kategoriya statistikasi - oddiy ko'rinish"""
    categories = load_json(CATEGORIES_FILE)
    category = next((c for c in categories["categories"] if c["id"] == category_id), None)
    
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    user_role = current_user.get("role")
    if user_role != "super_admin":
        if user_role not in category.get("allowedRoles", []):
            raise HTTPException(status_code=403, detail="Bu kategoriyaga ruxsatingiz yo'q")
    
    stats_data = load_json(STATISTICS_FILE)
    
    if category_id not in stats_data["statistics"]:
        return {
            "categoryId": category_id,
            "categoryName": category["name"],
            "statistics": [],
            "total": 0
        }
    
    category_stats = stats_data["statistics"][category_id]
    
    # Oddiy ko'rinish
    simple_stats = []
    for username, data in category_stats["users"].items():
        simple_stats.append({
            "username": username,
            "testCount": data["testCount"],
            "percentage": data["averagePercentage"]
        })
    
    # Foizga ko'ra sortlash
    simple_stats.sort(key=lambda x: x["percentage"], reverse=True)
    
    return {
        "categoryId": category_id,
        "categoryName": category_stats["categoryName"],
        "statistics": simple_stats,
        "total": len(simple_stats)
    }


@app.get("/api/results")
async def get_results(current_user: dict = Depends(verify_token)):
    data = load_json(RESULTS_FILE)
    
    if current_user.get("role") == "super_admin":
        return {"results": data["results"]}
    else:
        user_results = [r for r in data["results"] if r["username"] == current_user["sub"]]
        return {"results": user_results}

@app.get("/api/results/category/{category_id}")
async def get_category_results(category_id: str, current_user: dict = Depends(verify_token)):
    data = load_json(RESULTS_FILE)
    
    if current_user.get("role") == "super_admin":
        results = [r for r in data["results"] if r["categoryId"] == category_id]
    else:
        results = [
            r for r in data["results"]
            if r["categoryId"] == category_id and r["username"] == current_user["sub"]
        ]
    
    return {"results": results, "categoryId": category_id}

@app.get("/api/users")
async def get_users(current_user: dict = Depends(verify_token)):
    """Barcha userlarni ko'rish"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can view users")
    
    data = load_json(USERS_FILE)
    
    # Parollarni olib tashlash
    users_list = []
    for user in data["users"]:
        users_list.append({
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "created_at": user["created_at"]
        })
    
    return {
        "success": True,
        "users": users_list,
        "total": len(users_list)
    }

@app.get("/api/users/{user_id}")
async def get_user_detail(user_id: str, current_user: dict = Depends(verify_token)):
    """Bitta user tafsilotlari"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can view user details")
    
    data = load_json(USERS_FILE)
    user = next((u for u in data["users"] if u["id"] == user_id), None)
    
    if not user:
        raise HTTPException(status_code=404, detail="User topilmadi")
    
    # Parolsiz qaytarish
    user_info = {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "created_at": user["created_at"]
    }
    
    # User natijalarini qo'shish
    results_data = load_json(RESULTS_FILE)
    user_results = [r for r in results_data["results"] if r["username"] == user["username"]]
    
    return {
        "success": True,
        "user": user_info,
        "totalTests": len(user_results),
        "recentResults": user_results[-5:]  # Oxirgi 5 ta natija
    }

@app.delete("/api/users/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(verify_token)):
    """Userni o'chirish"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can delete users")
    
    data = load_json(USERS_FILE)
    user = next((u for u in data["users"] if u["id"] == user_id), None)
    
    if not user:
        raise HTTPException(status_code=404, detail="User topilmadi")
    
    # Super adminni o'chirish mumkin emas
    if user["role"] == "super_admin":
        raise HTTPException(status_code=403, detail="Cannot delete super admin")
    
    # Userni o'chirish
    data["users"] = [u for u in data["users"] if u["id"] != user_id]
    save_json(USERS_FILE, data)
    
    return {
        "success": True,
        "message": f"User {user['username']} o'chirildi"
    }

@app.put("/api/users/{user_id}/role")
async def update_user_role(user_id: str, new_role: dict, current_user: dict = Depends(verify_token)):
    """User rolini o'zgartirish"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can update user roles")
    
    data = load_json(USERS_FILE)
    user_index = next((i for i, u in enumerate(data["users"]) if u["id"] == user_id), None)
    
    if user_index is None:
        raise HTTPException(status_code=404, detail="User topilmadi")
    
    # Super adminning rolini o'zgartirish mumkin emas
    if data["users"][user_index]["role"] == "super_admin":
        raise HTTPException(status_code=403, detail="Cannot change super admin role")
    
    data["users"][user_index]["role"] = new_role.get("role")
    data["users"][user_index]["updated_at"] = datetime.now().isoformat()
    save_json(USERS_FILE, data)
    
    return {
        "success": True,
        "message": "User roli yangilandi",
        "user": {
            "id": data["users"][user_index]["id"],
            "username": data["users"][user_index]["username"],
            "role": data["users"][user_index]["role"]
        }
    }

@app.get("/")
async def root():
    return {
        "message": "Quiz System API - Yaxshilangan Versiya",
        "version": "3.0",
        "endpoints": {
            "POST /api/login": "Login",
            "POST /api/register": "Register",
            "GET /api/roles": "Rollar ro'yxati",
            "GET /api/categories": "Kategoriyalar",
            "POST /api/categories": "Kategoriya yaratish",
            "POST /api/questions": "Savollar qo'shish",
            "GET /api/categories/{id}/questions": "Kategoriya savollari",
            "POST /api/check": "Javoblarni tekshirish",
            "POST /api/submit-result": "Telegramga yuborish",
            "GET /api/statistics": "Barcha statistika",
            "GET /api/statistics/{id}": "Kategoriya statistikasi",
            "GET /api/users": "Userlar ro'yxati (super admin)",
            "GET /api/users/{id}": "User tafsilotlari",
            "DELETE /api/users/{id}": "Userni o'chirish",
            "PUT /api/users/{id}/role": "User rolini o'zgartirish"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8050)