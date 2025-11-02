import mysql.connector
from mysql.connector import Error
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List, Tuple, Any
from decimal import Decimal
import logging
import json
import csv
import os
from pathlib import Path

# Third-party imports (install with: pip install bcrypt colorama python-dotenv)
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    import hashlib
    BCRYPT_AVAILABLE = False
    print("Warning: bcrypt not installed. Using SHA256 (less secure). Install with: pip install bcrypt")

try:
    from colorama import Fore, Style, init as colorama_init
    COLORAMA_AVAILABLE = True
    try:
        # Initialize colorama; some environments (IDLE) may not support ANSI codes
        colorama_init(autoreset=True)
    except Exception:
        # Ignore initialization errors and continue without color if needed
        pass
except ImportError:
    # Fallback if colorama isn't installed
    COLORAMA_AVAILABLE = False
    class _NoColor:
        RESET_ALL = BRIGHT = ''
        RED = GREEN = YELLOW = BLUE = CYAN = MAGENTA = ''
    Fore = _NoColor()
    Style = _NoColor()

try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Application configuration with environment variable support"""
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'admin')
    DB_NAME = os.getenv('DB_NAME', 'calorie_calculator')
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = 'calorie_calculator.log'
    
    # Activity level multipliers for TDEE calculation
    ACTIVITY_MULTIPLIERS = {
        'Sedentary': 1.2,
        'Light': 1.375,
        'Moderate': 1.55,
        'Active': 1.725,
        'Very Active': 1.9
    }
    
    # BMI categories
    BMI_CATEGORIES = {
        'Underweight': (0, 18.5),
        'Normal': (18.5, 25),
        'Overweight': (25, 30),
        'Obese': (30, 100)
    }
    
    # Calorie adjustment for weight goals (calories per day)
    GOAL_CALORIE_ADJUSTMENT = {
        'lose': -500,  # ~0.5kg per week
        'maintain': 0,
        'gain': 300    # ~0.3kg per week
    }

    MEAL_TYPES = ['Breakfast', 'Lunch', 'Dinner', 'Snack']


# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging():
    """Configure logging for the application"""
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(Config.LOG_FILE),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def print_header(text: str, char: str = "=", width: int = 60) -> None:
    """Print a formatted header"""
    if COLORAMA_AVAILABLE:
        print(f"\n{Fore.CYAN}{char * width}")
        print(f"{text.center(width)}")
        print(f"{char * width}{Style.RESET_ALL}")
    else:
        print(f"\n{char * width}")
        print(text.center(width))
        print(char * width)


def print_success(message: str) -> None:
    """Print success message"""
    symbol = "✓" if COLORAMA_AVAILABLE else "[OK]"
    color = Fore.GREEN if COLORAMA_AVAILABLE else ""
    reset = Style.RESET_ALL if COLORAMA_AVAILABLE else ""
    print(f"{color}{symbol} {message}{reset}")


def print_error(message: str) -> None:
    """Print error message"""
    symbol = "✗" if COLORAMA_AVAILABLE else "[ERROR]"
    color = Fore.RED if COLORAMA_AVAILABLE else ""
    reset = Style.RESET_ALL if COLORAMA_AVAILABLE else ""
    print(f"{color}{symbol} {message}{reset}")


def print_warning(message: str) -> None:
    """Print warning message"""
    symbol = "⚠" if COLORAMA_AVAILABLE else "[WARNING]"
    color = Fore.YELLOW if COLORAMA_AVAILABLE else ""
    reset = Style.RESET_ALL if COLORAMA_AVAILABLE else ""
    print(f"{color}{symbol} {message}{reset}")


def print_info(message: str) -> None:
    """Print info message"""
    symbol = "ℹ" if COLORAMA_AVAILABLE else "[INFO]"
    color = Fore.BLUE if COLORAMA_AVAILABLE else ""
    reset = Style.RESET_ALL if COLORAMA_AVAILABLE else ""
    print(f"{color}{symbol} {message}{reset}")


def print_progress_bar(current: float, target: float, width: int = 30, label: str = "") -> None:
    """Print a progress bar"""
    if target <= 0:
        percentage = 0
    else:
        percentage = min((current / target) * 100, 100)
    
    filled = int(width * percentage / 100)
    bar = '█' * filled + '░' * (width - filled)
    
    if COLORAMA_AVAILABLE:
        color = Fore.GREEN if percentage >= 100 else Fore.YELLOW if percentage >= 75 else Fore.RED
        print(f"{label} [{color}{bar}{Style.RESET_ALL}] {percentage:.1f}%")
    else:
        print(f"{label} [{bar}] {percentage:.1f}%")


def get_positive_float(prompt: str, max_value: Optional[float] = None) -> float:
    """Get a positive float from user with validation"""
    while True:
        try:
            value = float(input(prompt))
            if value <= 0:
                print_error("Please enter a positive number")
                continue
            if max_value and value > max_value:
                print_error(f"Value too large. Maximum: {max_value}")
                continue
            return value
        except ValueError:
            print_error("Invalid input. Please enter a number")


def get_positive_int(prompt: str, min_value: int = 1, max_value: Optional[int] = None) -> int:
    """Get a positive integer from user with validation"""
    while True:
        try:
            value = int(input(prompt))
            if value < min_value:
                print_error(f"Please enter a number >= {min_value}")
                continue
            if max_value and value > max_value:
                print_error(f"Value too large. Maximum: {max_value}")
                continue
            return value
        except ValueError:
            print_error("Invalid input. Please enter a whole number")


def get_choice(prompt: str, options: List[str]) -> str:
    """Get a choice from a list of options"""
    while True:
        choice = input(prompt).strip()
        if choice in options:
            return choice
        print_error(f"Invalid choice. Please select from: {', '.join(options)}")


def confirm_action(message: str) -> bool:
    """Ask user to confirm an action"""
    response = input(f"{message} (y/n): ").strip().lower()
    return response in ['y', 'yes']

def get_date_input(prompt: str, default_to_today: bool = False) -> Optional[date]:
    """Get a date input from the user (YYYY-MM-DD)"""
    while True:
        date_str = input(prompt).strip()
        if not date_str:
            if default_to_today:
                return date.today()
            return None
            
        try:
            input_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            return input_date
        except ValueError:
            print_error("Invalid date format. Please use YYYY-MM-DD.")


# ============================================================================
# VALIDATORS
# ============================================================================

class Validator:
    """Input validation utilities"""
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Basic email validation"""
        return '@' in email and '.' in email.split('@')[1]
    
    @staticmethod
    def validate_age(age: int) -> bool:
        """Validate age is in reasonable range"""
        return 1 <= age <= 150
    
    @staticmethod
    def validate_height(height: float) -> bool:
        """Validate height in cm"""
        return 30 <= height <= 300
    
    @staticmethod
    def validate_weight(weight: float) -> bool:
        """Validate weight in kg"""
        return 2 <= weight <= 500
    
    @staticmethod
    def validate_password(password: str) -> Tuple[bool, str]:
        """Validate password strength"""
        if len(password) < 6:
            return False, "Password must be at least 6 characters long"
        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one digit"
        if not any(c.isalpha() for c in password):
            return False, "Password must contain at least one letter"
        return True, "Password is valid"


# ============================================================================
# PASSWORD HASHING
# ============================================================================

class PasswordHasher:
    """Handle password hashing with bcrypt or SHA256 fallback"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password"""
        if BCRYPT_AVAILABLE:
            return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        else:
            return hashlib.sha256(password.encode('utf-8')).hexdigest()
    
    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verify a password against its hash"""
        if BCRYPT_AVAILABLE:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        else:
            return hashlib.sha256(password.encode('utf-8')).hexdigest() == hashed


# ============================================================================
# ENHANCED CALORIE CALCULATOR - MAIN CLASS
# ============================================================================

class EnhancedCalorieCalculator:
    """
    Enhanced Calorie Calculator with advanced features:
    - BMI calculation and health insights
    - Weight tracking over time
    - Goal setting and progress monitoring
    - Water intake tracking
    - Advanced reporting
    - Data export capabilities
    """
    
    def __init__(self):
        self.connection: Optional[mysql.connector.MySQLConnection] = None
        self.current_user: Optional[Dict[str, Any]] = None
        self.connect_to_database()
        self.setup_database()
        logger.info("Application initialized")
    
    # ========================================================================
    # DATABASE CONNECTION
    # ========================================================================
    
    def connect_to_database(self) -> bool:
        """Establish database connection"""
        try:
            self.connection = mysql.connector.connect(
                host=Config.DB_HOST,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                # Initial connection may not specify DB_NAME if it doesn't exist yet
            )
            if self.connection.is_connected():
                print_success("Database connection established")
                logger.info("Database connection established")
                return True
        except Error as e:
            print_error(f"Database connection failed: {e}")
            logger.error(f"Database connection error: {e}")
            self.connection = None # Ensure connection is None on failure
            return False
    
    def setup_database(self) -> None:
        """Initialize database schema with enhanced tables"""
        if not self.connection:
            print_error("Cannot setup database: No connection.")
            return

        try:
            cursor = self.connection.cursor()
            
            # Create database if not exists
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {Config.DB_NAME}")
            cursor.execute(f"USE {Config.DB_NAME}")
            
            # Enhanced users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    age INT CHECK (age > 0 AND age < 150),
                    gender ENUM('Male','Female','Other') NOT NULL,
                    height_cm DECIMAL(5,2) CHECK (height_cm > 0),
                    weight_kg DECIMAL(5,2) CHECK (weight_kg > 0),
                    activity_level ENUM('Sedentary','Light','Moderate','Active','Very Active') NOT NULL,
                    goal_type ENUM('lose','maintain','gain') DEFAULT 'maintain',
                    goal_weight_kg DECIMAL(5,2),
                    daily_calorie_goal INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_username (username),
                    INDEX idx_email (email)
                )
            ''')
            
            # Food items table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS food_items (
                    food_id INT AUTO_INCREMENT PRIMARY KEY,
                    food_name VARCHAR(100) NOT NULL,
                    calories_per_100g DECIMAL(6,2),
                    protein_g DECIMAL(6,2),
                    carbs_g DECIMAL(6,2),
                    fat_g DECIMAL(6,2),
                    category VARCHAR(50),
                    INDEX idx_food_name (food_name),
                    INDEX idx_category (category)
                )
            ''')
            
            # Daily intake table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_intake (
                    intake_id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    food_id INT NOT NULL,
                    quantity_g DECIMAL(6,2) NOT NULL,
                    intake_date DATE NOT NULL,
                    meal_type ENUM('Breakfast','Lunch','Dinner','Snack') NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (food_id) REFERENCES food_items(food_id) ON DELETE RESTRICT,
                    UNIQUE KEY unique_intake (user_id, food_id, intake_date, meal_type),
                    INDEX idx_user_date (user_id, intake_date),
                    INDEX idx_date (intake_date)
                )
            ''')
            
            # Weight tracking table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS weight_tracking (
                    tracking_id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    weight_kg DECIMAL(5,2) NOT NULL,
                    bmi DECIMAL(4,2),
                    recorded_date DATE UNIQUE NOT NULL, -- Added UNIQUE constraint for robust tracking
                    notes TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    INDEX idx_user_date (user_id, recorded_date)
                )
            ''')
            
            # Water intake table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS water_intake (
                    water_id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    amount_ml INT NOT NULL,
                    intake_date DATE NOT NULL,
                    intake_time TIME,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    INDEX idx_user_date (user_id, intake_date)
                )
            ''')
            
            self.connection.commit()
            print_success("Database tables initialized")
            logger.info("Database schema setup completed")
            
            # Insert sample foods if table is empty
            self.insert_sample_foods()
            
        except Error as e:
            print_error(f"Database setup failed: {e}")
            logger.error(f"Database setup error: {e}")
        finally:
             if cursor:
                 cursor.close()
    
    def insert_sample_foods(self) -> None:
        """Insert sample food items if database is empty"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM food_items")
            count = cursor.fetchone()[0]
            
            if count == 0:
                sample_foods = [
                    # Foods (Name, Calories/100g, Protein, Carbs, Fat, Category)
                    ('Apple', 52, 0.3, 14, 0.2, 'Fruit'),
                    ('Banana', 89, 1.1, 23, 0.3, 'Fruit'),
                    ('Orange', 47, 0.9, 12, 0.1, 'Fruit'),
                    ('Mango', 60, 0.8, 15, 0.4, 'Fruit'),
                    ('Grapes', 69, 0.7, 18, 0.2, 'Fruit'),
                    
                    ('Broccoli', 34, 2.8, 7, 0.4, 'Vegetable'),
                    ('Potato', 77, 2, 17, 0.1, 'Vegetable'),
                    ('Carrot', 41, 0.9, 10, 0.2, 'Vegetable'),
                    ('Spinach', 23, 2.9, 3.6, 0.4, 'Vegetable'),
                    ('Tomato', 18, 0.9, 3.9, 0.2, 'Vegetable'),
                    
                    ('Chicken Breast', 165, 31, 0, 3.6, 'Protein'),
                    ('Egg', 155, 13, 1.1, 11, 'Protein'),
                    ('Salmon', 208, 20, 0, 13, 'Protein'),
                    ('Tuna', 132, 28, 0, 1.3, 'Protein'),
                    ('Tofu', 76, 8, 1.9, 4.8, 'Protein'),
                    
                    ('Brown Rice', 111, 2.6, 23, 0.9, 'Grains'),
                    ('Whole Wheat Bread', 265, 13, 51, 4.4, 'Grains'),
                    ('Oatmeal', 68, 2.4, 12, 1.4, 'Grains'),
                    ('Quinoa', 120, 4.4, 21, 1.9, 'Grains'),
                    ('Pasta', 131, 5, 25, 1.1, 'Grains'),
                    
                    ('Milk', 42, 3.4, 5, 1, 'Dairy'),
                    ('Yogurt', 59, 10, 3.6, 0.4, 'Dairy'),
                    ('Cheese', 402, 25, 1.3, 33, 'Dairy'),
                    ('Greek Yogurt', 59, 10, 3.6, 0.4, 'Dairy'),
                    
                    ('Almonds', 579, 21, 22, 50, 'Nuts'),
                    ('Peanuts', 567, 26, 16, 49, 'Nuts'),
                    ('Walnuts', 654, 15, 14, 65, 'Nuts'),
                    ('Chia Seeds', 486, 17, 42, 31, 'Seeds'),
                ]
                
                cursor.executemany('''
                    INSERT INTO food_items (food_name, calories_per_100g, protein_g, carbs_g, fat_g, category)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', sample_foods)
                
                self.connection.commit()
                print_success(f"Inserted {len(sample_foods)} sample foods")
                logger.info(f"Inserted {len(sample_foods)} sample food items")
            
        except Error as e:
            print_error(f"Error inserting sample foods: {e}")
            logger.error(f"Sample foods insertion error: {e}")
        finally:
            if cursor:
                 cursor.close()
    
    # ========================================================================
    # USER MANAGEMENT
    # ========================================================================
    
    def register_user(self) -> bool:
        """Register a new user with enhanced profile"""
        print_header("USER REGISTRATION")
        
        # Username
        username = input("Enter username: ").strip()
        if not username:
            print_error("Username cannot be empty")
            return False
        
        # Password with validation
        while True:
            password = input("Enter password: ")
            is_valid, message = Validator.validate_password(password)
            if is_valid:
                confirm_password = input("Confirm password: ")
                if password == confirm_password:
                    break
                else:
                    print_error("Passwords do not match")
            else:
                print_error(message)
        
        # Email with validation
        while True:
            email = input("Enter email: ").strip()
            if Validator.validate_email(email):
                break
            print_error("Invalid email format")
        
        # Age with validation
        age = get_positive_int("Enter age: ", min_value=1, max_value=150)
        
        # Gender
        print("\nGender Options:")
        print("1. Male")
        print("2. Female")
        print("3. Other")
        gender_choice = get_choice("Select gender (1-3): ", ['1', '2', '3'])
        gender = {'1': 'Male', '2': 'Female', '3': 'Other'}[gender_choice]
        
        # Height with validation
        height = get_positive_float("Enter height in cm: ", max_value=300)
        
        # Weight with validation
        weight = get_positive_float("Enter current weight in kg: ", max_value=500)
        
        # Activity level
        print("\nActivity Levels:")
        print("1. Sedentary (little or no exercise)")
        print("2. Light (light exercise 1-3 days/week)")
        print("3. Moderate (moderate exercise 3-5 days/week)")
        print("4. Active (hard exercise 6-7 days/week)")
        print("5. Very Active (very hard exercise, physical job)")
        activity_choice = get_choice("Select activity level (1-5): ", ['1', '2', '3', '4', '5'])
        activity_level = {
            '1': 'Sedentary',
            '2': 'Light',
            '3': 'Moderate',
            '4': 'Active',
            '5': 'Very Active'
        }[activity_choice]
        
        # Goal setting
        print("\nGoal Setting:")
        print("1. Lose weight")
        print("2. Maintain weight")
        print("3. Gain weight")
        goal_choice = get_choice("Select your goal (1-3): ", ['1', '2', '3'])
        goal_type = {'1': 'lose', '2': 'maintain', '3': 'gain'}[goal_choice]
        
        goal_weight = None
        if goal_type != 'maintain':
            goal_weight = get_positive_float(f"Enter target weight in kg: ", max_value=500)
        
        # Calculate daily calorie goal
        bmr = self.calculate_bmr_static(weight, height, age, gender)
        multiplier = Config.ACTIVITY_MULTIPLIERS[activity_level]
        tdee = bmr * multiplier
        daily_calorie_goal = int(tdee + Config.GOAL_CALORIE_ADJUSTMENT[goal_type])
        
        cursor = None
        try:
            cursor = self.connection.cursor()
            hashed_password = PasswordHasher.hash_password(password)
            
            cursor.execute('''
                INSERT INTO users 
                (username, password, email, age, gender, height_cm, weight_kg, 
                 activity_level, goal_type, goal_weight_kg, daily_calorie_goal)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (username, hashed_password, email, age, gender, height, weight,
                  activity_level, goal_type, goal_weight, daily_calorie_goal))
            
            self.connection.commit()
            user_id = cursor.lastrowid
            
            # Add initial weight tracking entry
            self.add_weight_entry_internal(user_id, weight, date.today())
            
            print_success("User registered successfully!")
            print_info(f"Your daily calorie target: {daily_calorie_goal} calories")
            logger.info(f"New user registered: {username}")
            
            return True
            
        except Error as e:
            # Check for duplicate entry error (e.g., username or email exists)
            if 'Duplicate entry' in str(e):
                print_error("Registration failed. Username or email already exists.")
            else:
                print_error(f"Registration failed: {e}")
            logger.error(f"User registration error: {e}")
            return False
        finally:
             if cursor:
                 cursor.close()

    
    def login_user(self) -> bool:
        """Authenticate and login user"""
        print_header("USER LOGIN")
        
        username = input("Username: ").strip()
        password = input("Password: ")
        
        cursor = None
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute(
                'SELECT user_id, username, password FROM users WHERE username = %s',
                (username,)
            )
            user = cursor.fetchone()
            
            if user and PasswordHasher.verify_password(password, user['password']):
                self.current_user = {
                    'user_id': user['user_id'],
                    'username': user['username']
                }
                print_success(f"Welcome back, {user['username']}!")
                logger.info(f"User logged in: {username}")
                return True
            else:
                print_error("Invalid username or password")
                logger.warning(f"Failed login attempt for: {username}")
                return False
                
        except Error as e:
            print_error(f"Login failed: {e}")
            logger.error(f"Login error: {e}")
            return False
        finally:
             if cursor:
                 cursor.close()
    
    def logout_user(self) -> None:
        """Logout current user"""
        if self.current_user:
            username = self.current_user['username']
            self.current_user = None
            print_success(f"Goodbye, {username}!")
            logger.info(f"User logged out: {username}")
    
    # ========================================================================
    # CALCULATIONS
    # ========================================================================
    
    @staticmethod
    def calculate_bmr_static(weight: float, height: float, age: int, gender: str) -> float:
        """Calculate Basal Metabolic Rate using Mifflin-St Jeor Equation"""
        if gender.lower() == 'male':
            bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
        else:
            bmr = (10 * weight) + (6.25 * height) - (5 * age) - 161
        
        return round(bmr, 2)
    
    @staticmethod
    def calculate_bmi(weight: float, height: float) -> float:
        """Calculate Body Mass Index: weight(kg) / (height(m)^2)"""
        height_m = height / 100
        bmi = weight / (height_m ** 2)
        return round(bmi, 2)
    
    @staticmethod
    def get_bmi_category(bmi: float) -> str:
        """Get BMI category from BMI value"""
        for category, (min_bmi, max_bmi) in Config.BMI_CATEGORIES.items():
            if min_bmi <= bmi < max_bmi:
                return category
        return "Unknown"
    
    @staticmethod
    def get_bmi_recommendation(bmi: float) -> str:
        """Get health recommendation based on BMI"""
        category = EnhancedCalorieCalculator.get_bmi_category(bmi)
        
        recommendations = {
            'Underweight': "Consider consulting a nutritionist to develop a healthy weight gain plan.",
            'Normal': "Great job! Maintain your current lifestyle and healthy eating habits.",
            'Overweight': "Consider increasing physical activity and reviewing your diet with a professional.",
            'Obese': "We recommend consulting a healthcare provider for a personalized weight management plan."
        }
        
        return recommendations.get(category, "Consult a healthcare professional for personalized advice.")
    
    def calculate_bmr(self, user_id: int) -> Optional[float]:
        """Calculate BMR for a user from database"""
        cursor = None
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT age, gender, weight_kg, height_cm 
                FROM users 
                WHERE user_id = %s
            """, (user_id,))
            user = cursor.fetchone()
            
            if not user:
                return None
            
            weight = float(user['weight_kg'])
            height = float(user['height_cm'])
            age = int(user['age'])
            gender = user['gender']
            
            return self.calculate_bmr_static(weight, height, age, gender)
            
        except Error as e:
            logger.error(f"BMR calculation error: {e}")
            return None
        finally:
             if cursor:
                 cursor.close()
    
    def calculate_daily_calories(self, user_id: int) -> Optional[int]:
        """Calculate daily calorie needs (TDEE) for a user"""
        cursor = None
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT activity_level, daily_calorie_goal 
                FROM users 
                WHERE user_id = %s
            """, (user_id,))
            user = cursor.fetchone()
            
            if not user:
                return None
            
            if user['daily_calorie_goal']:
                return int(user['daily_calorie_goal'])
            
            bmr = self.calculate_bmr(user_id)
            if bmr is None:
                return None
            
            multiplier = Config.ACTIVITY_MULTIPLIERS.get(user['activity_level'], 1.2)
            tdee = bmr * multiplier
            
            return round(tdee)
            
        except Error as e:
            logger.error(f"Daily calorie calculation error: {e}")
            return None
        finally:
             if cursor:
                 cursor.close()
    
    # ========================================================================
    # USER PROFILE
    # ========================================================================
    
    def show_user_profile(self) -> None:
        """Display comprehensive user profile with health metrics"""
        if not self.current_user:
            print_error("Please login first")
            return
        
        cursor = None
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM users WHERE user_id = %s
            """, (self.current_user['user_id'],))
            user = cursor.fetchone()
            
            if not user:
                print_error("User not found")
                return
            
            print_header("USER PROFILE")
            
            # Basic info
            print(f"\n{Fore.CYAN}Basic Information:{Style.RESET_ALL}")
            print(f"  Username: {user['username']}")
            print(f"  Email: {user['email']}")
            print(f"  Age: {user['age']} years")
            print(f"  Gender: {user['gender']}")
            
            # Physical stats
            weight = float(user['weight_kg'])
            height = float(user['height_cm'])
            
            print(f"\n{Fore.CYAN}Physical Stats:{Style.RESET_ALL}")
            print(f"  Height: {height:.1f} cm")
            print(f"  Current Weight: {weight:.1f} kg")
            print(f"  Activity Level: {user['activity_level']}")
            
            # BMI calculation
            bmi = self.calculate_bmi(weight, height)
            bmi_category = self.get_bmi_category(bmi)
            
            color = Fore.GREEN if bmi_category == 'Normal' else Fore.YELLOW if bmi_category in ['Underweight', 'Overweight'] else Fore.RED
            print(f"  BMI: {color}{bmi:.1f} ({bmi_category}){Style.RESET_ALL}")
            
            # Goal info
            if user['goal_type'] and user['goal_type'] != 'maintain':
                print(f"\n{Fore.CYAN}Goal:{Style.RESET_ALL}")
                goal_text = "Lose Weight" if user['goal_type'] == 'lose' else "Gain Weight"
                print(f"  Goal Type: {goal_text}")
                if user['goal_weight_kg']:
                    goal_weight = float(user['goal_weight_kg'])
                    print(f"  Target Weight: {goal_weight:.1f} kg")
                    diff = abs(weight - goal_weight)
                    print(f"  Remaining: {diff:.1f} kg")
            
            # Calorie needs
            bmr = self.calculate_bmr(self.current_user['user_id'])
            daily_calories = self.calculate_daily_calories(self.current_user['user_id'])
            
            print(f"\n{Fore.CYAN}Metabolic Info:{Style.RESET_ALL}")
            if bmr:
                print(f"  Basal Metabolic Rate: {bmr:.0f} cal/day")
            if daily_calories:
                print(f"  Daily Calorie Target: {daily_calories} cal/day")
            
            # Health recommendation
            print(f"\n{Fore.CYAN}Health Recommendation:{Style.RESET_ALL}")
            recommendation = self.get_bmi_recommendation(bmi)
            print(f"  {recommendation}")
            
            # Account info
            print(f"\n{Fore.CYAN}Account:{Style.RESET_ALL}")
            print(f"  Member Since: {user['created_at'].strftime('%Y-%m-%d')}")
            
        except Error as e:
            print_error(f"Error displaying profile: {e}")
            logger.error(f"Profile display error: {e}")
        finally:
             if cursor:
                 cursor.close()
    
    # ========================================================================
    # WEIGHT TRACKING
    # ========================================================================
    
    def add_weight_entry_internal(self, user_id: int, weight: float, recorded_date: date) -> None:
        """Internal function to add a weight entry and update user's profile weight."""
        cursor = None
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute("SELECT height_cm FROM users WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()
            
            if not user or not user['height_cm']:
                print_error("Cannot track weight: User height not found.")
                logger.warning(f"Weight tracking failed for user {user_id}: height missing.")
                return

            height = float(user['height_cm'])
            bmi = self.calculate_bmi(weight, height)
            
            # 1. Insert/Update into weight_tracking table
            # Using INSERT ... ON DUPLICATE KEY UPDATE because recorded_date is UNIQUE
            cursor.execute('''
                INSERT INTO weight_tracking (user_id, weight_kg, bmi, recorded_date)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE weight_kg = VALUES(weight_kg), bmi = VALUES(bmi)
            ''', (user_id, weight, bmi, recorded_date))
            
            # 2. Update the primary weight in the users table
            cursor.execute('''
                UPDATE users SET weight_kg = %s WHERE user_id = %s
            ''', (weight, user_id))

            self.connection.commit()
            logger.info(f"Weight entry added/updated and user weight updated for user {user_id}: {weight}kg (BMI: {bmi})")
            
        except Error as e:
            print_error(f"Database error during weight tracking: {e}")
            logger.error(f"Weight tracking database error: {e}")
        finally:
            if cursor:
                 cursor.close()


    def add_weight_entry(self) -> None:
        """User-facing method to record a new weight measurement."""
        if not self.current_user:
            print_error("Please login first to record your weight.")
            return

        print_header("RECORD NEW WEIGHT")
        
        # Get weight with validation
        weight = get_positive_float("Enter your current weight in kg: ", max_value=500)
        
        # Get date
        recorded_date = get_date_input("Enter date (YYYY-MM-DD, default is today): ", default_to_today=True)
        
        if recorded_date and recorded_date > date.today():
             print_error("Cannot record weight for a future date.")
             return
        
        if recorded_date: # Only proceed if a valid date was provided or defaulted
            # The internal function handles the INSERT/UPDATE logic
            self.add_weight_entry_internal(self.current_user['user_id'], weight, recorded_date)
            print_success(f"Weight of {weight:.1f} kg recorded for {recorded_date}.")
        
    # ========================================================================
    # FOOD MANAGEMENT
    # ========================================================================
    
    def search_food(self, search_term: str) -> List[Dict[str, Any]]:
        """Search food items by name or category."""
        cursor = None
        try:
            cursor = self.connection.cursor(dictionary=True)
            # Use LIKE for fuzzy searching
            query = """
                SELECT food_id, food_name, calories_per_100g, protein_g, carbs_g, fat_g, category 
                FROM food_items 
                WHERE food_name LIKE %s OR category LIKE %s
                LIMIT 10
            """
            search_pattern = f'%{search_term}%'
            cursor.execute(query, (search_pattern, search_pattern))
            results = cursor.fetchall()
            return results
        except Error as e:
            logger.error(f"Food search error: {e}")
            print_error("An error occurred during food search.")
            return []
        finally:
            if cursor:
                 cursor.close()

    def view_food_items(self) -> None:
        """Displays a list of sample and user-added food items."""
        print_header("FOOD DATABASE SEARCH")
        search_term = input("Search food by name or category (leave blank to view top 10): ").strip()

        foods = self.search_food(search_term)

        if not foods:
            print_warning(f"No food items found matching '{search_term}'.")
            return

        print(f"\n{Fore.GREEN}--- Found {len(foods)} Food Items ---{Style.RESET_ALL}")
        print("{:<5} {:<20} {:<10} {:<8} {:<8} {:<8} {:<10}".format(
            "ID", "Name", "Category", "Cal/100g", "Prot(g)", "Carbs(g)", "Fat(g)"
        ))
        print("=" * 70)
        
        for food in foods:
            print("{:<5} {:<20} {:<10} {:<8.1f} {:<8.1f} {:<8.1f} {:<10.1f}".format(
                food['food_id'],
                food['food_name'],
                food['category'][:9],
                float(food['calories_per_100g']),
                float(food['protein_g']),
                float(food['carbs_g']),
                float(food['fat_g'])
            ))
        print("=" * 70)

    # ========================================================================
    # DAILY INTAKE LOGGING
    # ========================================================================
    
    def log_daily_intake(self) -> None:
        """Allow user to log a food item consumed for a specific meal and date."""
        if not self.current_user:
            print_error("Please login first to log your food intake.")
            return

        print_header("LOG FOOD INTAKE")
        
        # 1. Select Food
        self.view_food_items()
        food_id = get_positive_int("Enter the Food ID to log: ")
        
        cursor = None
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM food_items WHERE food_id = %s", (food_id,))
            food = cursor.fetchone()
            
            if not food:
                print_error(f"Food with ID {food_id} not found.")
                return

            print_info(f"Logging: {Fore.YELLOW}{food['food_name']}{Style.RESET_ALL} ({food['calories_per_100g']} cal/100g)")
            
            # 2. Get Quantity
            quantity = get_positive_float("Enter quantity consumed in grams (g): ")

            # 3. Get Meal Type
            print("\nMeal Types:")
            for i, meal in enumerate(Config.MEAL_TYPES, 1):
                print(f"{i}. {meal}")
            meal_choice_idx = get_choice("Select meal type (1-4): ", [str(i) for i in range(1, len(Config.MEAL_TYPES) + 1)])
            meal_type = Config.MEAL_TYPES[int(meal_choice_idx) - 1]

            # 4. Get Date
            intake_date = get_date_input("Enter date consumed (YYYY-MM-DD, default is today): ", default_to_today=True)
            if intake_date and intake_date > date.today():
                 print_error("Cannot log food for a future date.")
                 return
            
            if not intake_date:
                print_error("A date is required for logging intake.")
                return

            # 5. Insert into daily_intake
            # Using INSERT ... ON DUPLICATE KEY UPDATE to allow updating quantity for the same food/meal/date
            cursor.execute('''
                INSERT INTO daily_intake (user_id, food_id, quantity_g, intake_date, meal_type)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE quantity_g = quantity_g + VALUES(quantity_g)
            ''', (self.current_user['user_id'], food_id, quantity, intake_date, meal_type))
            
            self.connection.commit()
            print_success(f"Logged {quantity:.1f}g of {food['food_name']} for {meal_type} on {intake_date}.")
            logger.info(f"User {self.current_user['user_id']} logged {quantity:.1f}g of food_id {food_id}")

        except Error as e:
            print_error(f"Error logging food intake: {e}")
            logger.error(f"Food intake logging error: {e}")
        finally:
            if cursor:
                 cursor.close()

    # ========================================================================
    # REPORTING AND SUMMARY
    # ========================================================================
    
    def get_daily_summary(self, target_date: date) -> Optional[Dict[str, float]]:
        """Calculate and return total macros and calories for a specific date."""
        cursor = None
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # SQL Query to join daily_intake with food_items and calculate total macros/calories
            query = """
                SELECT 
                    SUM(T1.quantity_g * (T2.calories_per_100g / 100)) AS total_calories,
                    SUM(T1.quantity_g * (T2.protein_g / 100)) AS total_protein,
                    SUM(T1.quantity_g * (T2.carbs_g / 100)) AS total_carbs,
                    SUM(T1.quantity_g * (T2.fat_g / 100)) AS total_fat
                FROM daily_intake T1
                JOIN food_items T2 ON T1.food_id = T2.food_id
                WHERE T1.user_id = %s AND T1.intake_date = %s
            """
            
            cursor.execute(query, (self.current_user['user_id'], target_date))
            summary = cursor.fetchone()
            
            if summary and summary['total_calories'] is not None:
                # Convert Decimals to float for easier use/display
                return {k: float(v) for k, v in summary.items()}
            else:
                return None
                
        except Error as e:
            logger.error(f"Daily summary error: {e}")
            print_error(f"Error retrieving daily summary: {e}")
            return None
        finally:
            if cursor:
                 cursor.close()

    def show_daily_report(self) -> None:
        """Display the daily calorie and macro consumption against the goal."""
        if not self.current_user:
            print_error("Please login first to view your daily report.")
            return

        print_header("DAILY NUTRITION REPORT")
        
        report_date = get_date_input("Enter date for the report (YYYY-MM-DD, default is today): ", default_to_today=True)
        if not report_date: return

        # Get Goal
        daily_goal = self.calculate_daily_calories(self.current_user['user_id'])
        if not daily_goal:
            print_error("Could not retrieve daily calorie goal. Please check your profile setup.")
            return

        # Get Summary
        summary = self.get_daily_summary(report_date)
        
        print(f"\n{Fore.MAGENTA}--- Report for {report_date} ---{Style.RESET_ALL}")
        
        if not summary:
            print_warning(f"No food intake recorded for {report_date}.")
            print(f"Daily Calorie Goal: {daily_goal} cal")
            return

        total_cal = summary['total_calories']
        remaining_cal = max(0, daily_goal - total_cal)
        
        # Calorie Progress
        print(f"\n{Fore.CYAN}CALORIE TRACKING:{Style.RESET_ALL}")
        print(f"  Consumed: {total_cal:.0f} cal")
        print(f"  Goal:     {daily_goal:.0f} cal")
        print(f"  Remaining: {remaining_cal:.0f} cal")
        print_progress_bar(total_cal, daily_goal, label="Progress")
        
        # Macro Summary
        print(f"\n{Fore.CYAN}MACRONUTRIENT BREAKDOWN:{Style.RESET_ALL}")
        print(f"  Protein: {summary['total_protein']:.1f} g")
        print(f"  Carbs:   {summary['total_carbs']:.1f} g")
        print(f"  Fat:     {summary['total_fat']:.1f} g")
        
        # Simple macro ratio (Optional: could add target macro ratios later)
        total_macros = summary['total_protein'] + summary['total_carbs'] + summary['total_fat']
        if total_macros > 0:
            p_pct = (summary['total_protein'] / total_macros) * 100
            c_pct = (summary['total_carbs'] / total_macros) * 100
            f_pct = (summary['total_fat'] / total_macros) * 100
            print(f"  (Ratio: P {p_pct:.0f}% / C {c_pct:.0f}% / F {f_pct:.0f}%)")

        if total_cal > daily_goal:
            print_warning(f"\n⚠️ You exceeded your daily calorie goal by {abs(remaining_cal):.0f} calories.")
        elif total_cal < daily_goal * 0.7:
             print_warning("\n⚠️ Intake is low. Ensure you are meeting a minimum healthy calorie intake.")


# ============================================================================
# MAIN APPLICATION LOOP
# ============================================================================

def main_menu(app: EnhancedCalorieCalculator):
    """Main application menu loop."""
    while True:
        print_header("CALORIE CALCULATOR MENU")
        
        if not app.current_user:
            print("1. Register")
            print("2. Login")
            print("3. Exit")
            choice = input("Enter choice: ").strip()
            
            if choice == '1':
                app.register_user()
            elif choice == '2':
                app.login_user()
            elif choice == '3':
                print_info("Exiting application. Goodbye!")
                break
            else:
                print_error("Invalid choice.")
        
        else:
            username = app.current_user['username']
            print_info(f"Logged in as: {Fore.YELLOW}{username}{Style.RESET_ALL}")
            print("1. View Profile & Goals")
            print("2. Log Food Intake")
            print("3. View Daily Report")
            print("4. Record New Weight")
            print("5. Search Food Database")
            # print("6. Track Water Intake (Future Feature)")
            print("6. Logout")
            print("7. Exit")
            choice = input("Enter choice: ").strip()

            if choice == '1':
                app.show_user_profile()
            elif choice == '2':
                app.log_daily_intake()
            elif choice == '3':
                app.show_daily_report()
            elif choice == '4':
                app.add_weight_entry()
            elif choice == '5':
                app.view_food_items()
            # elif choice == '6':
            #     # app.track_water_intake() # Placeholder
            #     pass 
            elif choice == '6':
                app.logout_user()
            elif choice == '7':
                print_info("Exiting application. Goodbye!")
                break
            else:
                print_error("Invalid choice.")

if __name__ == "__main__":
    app = EnhancedCalorieCalculator()
    # Only proceed if the database connection was successful
    if app.connection and app.connection.is_connected():
        main_menu(app)
    
    # Close connection cleanly upon exit
    if app.connection and app.connection.is_connected():
        app.connection.close()
        logger.info("Database connection closed.")