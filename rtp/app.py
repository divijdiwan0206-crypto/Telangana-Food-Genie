import math
import os
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# ─────────────────────────────────────────────────────────
#  CONFIG — set USE_MONGO=true in environment to use MongoDB
#  otherwise falls back to SQLite (for local dev)
# ─────────────────────────────────────────────────────────
USE_MONGO = os.environ.get("USE_MONGO", "false").lower() == "true"
MONGO_URI  = os.environ.get("MONGO_URI", "mongodb://localhost:27017/foodgenie")

app = Flask(__name__)
app.config['SECRET_KEY']                = os.environ.get('SECRET_KEY', os.urandom(32).hex())
app.config['REMEMBER_COOKIE_DURATION']  = timedelta(days=7)
app.config['SESSION_COOKIE_HTTPONLY']   = True
app.config['SESSION_COOKIE_SAMESITE']   = 'Lax'

# ─────────────────────────────────────────────────────────
#  DATABASE SETUP  (Mongo OR SQLite, unified interface)
# ─────────────────────────────────────────────────────────
if USE_MONGO:
    from flask_pymongo import PyMongo
    from bson import ObjectId
    app.config["MONGO_URI"] = MONGO_URI
    mongo = PyMongo(app)

    # ── Mongo User ──
    class User(UserMixin):
        def __init__(self, doc):
            self._id      = doc["_id"]
            self.email    = doc["email"]
            self.password = doc["password"]
        def get_id(self):
            return str(self._id)

    def get_user_by_id(uid):
        doc = mongo.db.users.find_one({"_id": ObjectId(uid)})
        return User(doc) if doc else None

    def get_user_by_email(email):
        doc = mongo.db.users.find_one({"email": email})
        return User(doc) if doc else None

    def create_user(email, hashed_pw):
        mongo.db.users.insert_one({"email": email, "password": hashed_pw})

    def add_review_db(restaurant_name, user_email, comment, stars, is_verified):
        mongo.db.reviews.insert_one({
            "restaurant_name": restaurant_name,
            "user_email":      user_email,
            "comment":         comment,
            "star_rating":     stars,
            "is_verified":     is_verified,
            "timestamp":       datetime.utcnow()
        })

    def get_reviews(restaurant_name):
        docs = mongo.db.reviews.find({"restaurant_name": restaurant_name})
        return list(docs)

else:
    from flask_sqlalchemy import SQLAlchemy
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///final_v11.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db = SQLAlchemy(app)

    class User(UserMixin, db.Model):
        id       = db.Column(db.Integer, primary_key=True)
        email    = db.Column(db.String(120), unique=True, nullable=False)
        password = db.Column(db.String(255), nullable=False)

    class Review(db.Model):
        id              = db.Column(db.Integer, primary_key=True)
        restaurant_name = db.Column(db.String(150))
        user_email      = db.Column(db.String(120))
        comment         = db.Column(db.Text)
        star_rating     = db.Column(db.Integer, default=5)
        is_verified     = db.Column(db.Boolean, default=False)
        timestamp       = db.Column(db.DateTime, default=datetime.utcnow)

    def get_user_by_id(uid):
        return User.query.get(int(uid))

    def get_user_by_email(email):
        return User.query.filter_by(email=email).first()

    def create_user(email, hashed_pw):
        db.session.add(User(email=email, password=hashed_pw))
        db.session.commit()

    def add_review_db(restaurant_name, user_email, comment, stars, is_verified):
        db.session.add(Review(
            restaurant_name=restaurant_name,
            user_email=user_email,
            comment=comment,
            star_rating=stars,
            is_verified=is_verified
        ))
        db.session.commit()

    def get_reviews(restaurant_name):
        return Review.query.filter_by(restaurant_name=restaurant_name).all()


# ─────────────────────────────────────────────────────────
#  LOGIN MANAGER
# ─────────────────────────────────────────────────────────
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)


# ─────────────────────────────────────────────────────────
#  CORE RESTAURANT DATASET
# ─────────────────────────────────────────────────────────
CORE_DATA = [
    {"name": "Paradise Biryani",         "cuisine": "Hyderabadi",          "type": "Legacy",         "lat": 17.4446, "lng": 78.4483, "dishes": "Mutton Dum Biryani",                "diet": "nonveg",  "hygiene": "4.2/5"},
    {"name": "Bawarchi",                 "cuisine": "Indian/Desi",          "type": "Iconic",         "lat": 17.4062, "lng": 78.4851, "dishes": "Chicken Biryani",                   "diet": "nonveg",  "hygiene": "4.0/5"},
    {"name": "Shah Ghouse",              "cuisine": "Hyderabadi",          "type": "Mughlai",        "lat": 17.3616, "lng": 78.4747, "dishes": "Special Haleem & Biryani",          "diet": "nonveg",  "hygiene": "3.8/5"},
    {"name": "Pista House",              "cuisine": "Mandi/Desi",          "type": "Restaurant",     "lat": 17.4400, "lng": 78.3480, "dishes": "Chicken Mandi",                     "diet": "nonveg",  "hygiene": "4.1/5"},
    {"name": "Biryani Zone",             "cuisine": "Hyderabadi",          "type": "Casual",         "lat": 17.4250, "lng": 78.4500, "dishes": "Dum Biryani",                       "diet": "nonveg",  "hygiene": "3.5/5"},
    {"name": "Rayalaseema Ruchulu",      "cuisine": "Andhra/South Indian", "type": "Authentic",      "lat": 17.4100, "lng": 78.4700, "dishes": "Spicy Chicken Curry & Rice",        "diet": "nonveg",  "hygiene": "3.7/5"},
    {"name": "Chutneys",                 "cuisine": "South Indian",        "type": "Vegetarian",     "lat": 17.4330, "lng": 78.4080, "dishes": "Pesarattu & Filter Coffee",         "diet": "veg",     "hygiene": "4.8/5"},
    {"name": "Southern Spice",           "cuisine": "South Indian",        "type": "Fine Dining",    "lat": 17.4400, "lng": 78.3950, "dishes": "Dosa & Sambar",                     "diet": "veg",     "hygiene": "4.6/5"},
    {"name": "Gokul Chat",               "cuisine": "Desi Snacks",         "type": "Street Food",    "lat": 17.3880, "lng": 78.4750, "dishes": "Papdi Chat & Pani Puri",            "diet": "veg",     "hygiene": "3.2/5"},
    {"name": "Alpha Hotel",              "cuisine": "South Indian",        "type": "Classic",        "lat": 17.3950, "lng": 78.4650, "dishes": "Idli & Vada",                       "diet": "veg",     "hygiene": "3.9/5"},
    {"name": "Mainland China",           "cuisine": "Chinese",             "type": "Fine Dining",    "lat": 17.4350, "lng": 78.4450, "dishes": "Dim Sum & Peking Duck",             "diet": "nonveg",  "hygiene": "4.7/5"},
    {"name": "Nanking",                  "cuisine": "Chinese",             "type": "Old School",     "lat": 17.4300, "lng": 78.4800, "dishes": "Manchurian & Fried Rice",           "diet": "both",    "hygiene": "3.6/5"},
    {"name": "Shang Palace",             "cuisine": "Chinese",             "type": "Fine Dining",    "lat": 17.4420, "lng": 78.3880, "dishes": "Cantonese Prawns & Dumplings",      "diet": "nonveg",  "hygiene": "4.9/5"},
    {"name": "Bercos",                   "cuisine": "Chinese/Asian",       "type": "Casual",         "lat": 17.4500, "lng": 78.3800, "dishes": "Noodles & Dragon Chicken",          "diet": "both",    "hygiene": "3.8/5"},
    {"name": "China Bistro",             "cuisine": "Chinese",             "type": "Bistro",         "lat": 17.4180, "lng": 78.3400, "dishes": "Schezwan Noodles & Momos",          "diet": "both",    "hygiene": "4.0/5"},
    {"name": "Yauatcha",                 "cuisine": "Chinese/Dim Sum",     "type": "Luxury",         "lat": 17.4370, "lng": 78.4490, "dishes": "Truffle Edamame Dumpling",          "diet": "both",    "hygiene": "4.9/5"},
    {"name": "Haiku",                    "cuisine": "Japanese",            "type": "Fine Dining",    "lat": 17.4210, "lng": 78.4310, "dishes": "Sushi & Ramen",                     "diet": "nonveg",  "hygiene": "4.8/5"},
    {"name": "Izumi",                    "cuisine": "Japanese",            "type": "Authentic",      "lat": 17.4280, "lng": 78.4180, "dishes": "Tonkotsu Ramen & Gyoza",            "diet": "nonveg",  "hygiene": "4.5/5"},
    {"name": "Sakura Restaurant",        "cuisine": "Japanese",            "type": "Restaurant",     "lat": 17.4150, "lng": 78.4400, "dishes": "Tempura & Miso Soup",               "diet": "both",    "hygiene": "4.4/5"},
    {"name": "Tokyo Ramen House",        "cuisine": "Japanese",            "type": "Ramen Bar",      "lat": 17.4510, "lng": 78.3850, "dishes": "Spicy Miso Ramen",                  "diet": "both",    "hygiene": "4.0/5"},
    {"name": "Goguryeo",                 "cuisine": "Korean",              "type": "Authentic",      "lat": 17.4450, "lng": 78.3500, "dishes": "Bulgogi & Korean BBQ",              "diet": "nonveg",  "hygiene": "4.1/5"},
    {"name": "K-Pop Kitchen",            "cuisine": "Korean",              "type": "Trendy",         "lat": 17.4490, "lng": 78.3680, "dishes": "Tteokbokki & Korean Fried Chicken", "diet": "both",    "hygiene": "4.4/5"},
    {"name": "Hanok Korean BBQ",         "cuisine": "Korean BBQ",          "type": "BBQ",            "lat": 17.4600, "lng": 78.3820, "dishes": "Galbi & Samgyeopsal",               "diet": "nonveg",  "hygiene": "4.5/5"},
    {"name": "Cream Stone",              "cuisine": "Ice Cream/Dessert",   "type": "Parlor",         "lat": 17.4290, "lng": 78.4060, "dishes": "Willy Wonka & Custom Mix-ins",      "diet": "veg",     "hygiene": "4.6/5"},
    {"name": "Concu",                    "cuisine": "Dessert/Bakery",      "type": "Patisserie",     "lat": 17.4330, "lng": 78.4050, "dishes": "Tiramisu & Macarons",               "diet": "veg",     "hygiene": "4.8/5"},
    {"name": "Gelato Italiano",          "cuisine": "Gelato/Italian",      "type": "Gelato Bar",     "lat": 17.4350, "lng": 78.4200, "dishes": "Pistachio Gelato & Affogato",       "diet": "veg",     "hygiene": "4.9/5"},
    {"name": "Theobroma",                "cuisine": "Bakery/Dessert",      "type": "Bakery Cafe",    "lat": 17.4420, "lng": 78.3880, "dishes": "Chocolate Truffle Cake & Brownies", "diet": "veg",     "hygiene": "4.7/5"},
    {"name": "Cafe Niloufer",            "cuisine": "Tea/Bakery",          "type": "Chai Point",     "lat": 17.3980, "lng": 78.4590, "dishes": "Osmania Biscuits & Irani Chai",     "diet": "veg",     "hygiene": "3.6/5"},
    {"name": "Roastery Coffee House",    "cuisine": "Coffee/Continental",  "type": "Cafe",           "lat": 17.4200, "lng": 78.4100, "dishes": "Cold Brew & Avocado Toast",         "diet": "veg",     "hygiene": "4.8/5"},
    {"name": "Starbucks",                "cuisine": "Coffee/Snacks",       "type": "Cafe",           "lat": 17.4300, "lng": 78.3900, "dishes": "Frappuccino & Java Chip",           "diet": "veg",     "hygiene": "4.9/5"},
    {"name": "Third Wave Coffee",        "cuisine": "Coffee",              "type": "Specialty Cafe", "lat": 17.4410, "lng": 78.3800, "dishes": "Single Origin Pour Over",           "diet": "veg",     "hygiene": "4.8/5"},
    {"name": "KFC",                      "cuisine": "Fast Food",           "type": "Global Chain",   "lat": 17.4400, "lng": 78.3800, "dishes": "Zinger Burger & Popcorn Chicken",   "diet": "nonveg",  "hygiene": "4.3/5"},
    {"name": "Pizza Hut",                "cuisine": "Italian/Fast Food",   "type": "Pizzeria",       "lat": 17.4500, "lng": 78.3700, "dishes": "Pan Pizza & Garlic Bread",          "diet": "both",    "hygiene": "4.2/5"},
    {"name": "McDonald's",               "cuisine": "Fast Food/Burgers",   "type": "Global Chain",   "lat": 17.4450, "lng": 78.3620, "dishes": "McAloo Tikki & McFlurry",           "diet": "both",    "hygiene": "4.4/5"},
    {"name": "Domino's Pizza",           "cuisine": "Pizza/Fast Food",     "type": "Pizzeria",       "lat": 17.4320, "lng": 78.3600, "dishes": "Farmhouse Pizza & Garlic Twists",   "diet": "both",    "hygiene": "4.3/5"},
]

CRAVING_EXPAND = {
    "biryani":      ["biryani", "hyderabadi", "mughlai", "dum", "rice", "indian"],
    "pizza":        ["pizza", "italian", "pizzeria", "dominos"],
    "burger":       ["burger", "fast food", "kfc", "mcdonalds", "american"],
    "chinese":      ["chinese", "noodles", "manchurian", "schezwan", "wok", "dim sum"],
    "japanese":     ["japanese", "sushi", "ramen", "tempura", "udon", "miso", "bento"],
    "ramen":        ["japanese", "ramen", "noodles", "tonkotsu", "miso"],
    "korean":       ["korean", "bibimbap", "kimchi", "bulgogi", "tteokbokki"],
    "coffee":       ["coffee", "cafe", "espresso", "brew", "latte"],
    "tea":          ["tea", "chai", "bakery", "irani"],
    "chaat":        ["chaat", "chat", "street food", "pani puri", "bhel"],
    "ice cream":    ["ice cream", "gelato", "frozen yogurt", "dessert", "parlor"],
    "dessert":      ["dessert", "bakery", "cake", "sweet", "ice cream", "gelato", "waffle"],
    "dosa":         ["south indian", "dosa", "idli", "vada", "indian"],
    "south indian": ["south indian", "dosa", "idli", "vada", "filter coffee"],
    "fast food":    ["fast food", "burger", "pizza", "kfc", "mcdonalds", "quick"],
    "all":          [],
}

OSM_AMENITY_TAGS = ["restaurant", "cafe", "fast_food", "ice_cream", "bakery", "food_court"]
OSM_CUISINE_MAP  = {
    "biryani": "biryani", "pizza": "pizza", "burger": "burger",
    "chinese": "chinese", "japanese": "japanese", "sushi": "sushi",
    "ramen": "ramen", "korean": "korean", "coffee": "coffee",
    "ice cream": "ice_cream", "dessert": "dessert", "south indian": "indian",
    "dosa": "indian", "fast food": "fast_food",
}

DISH_MAP = {
    "chinese":      ["Schezwan Noodles", "Dragon Chicken", "Dim Sum", "Manchurian"],
    "japanese":     ["Ramen", "Sushi Roll", "Tempura", "Gyoza"],
    "korean":       ["Bibimbap", "Kimchi Jjigae", "Korean Fried Chicken", "Bulgogi"],
    "indian":       ["Paneer Butter Masala", "Butter Chicken", "Dal Makhani"],
    "hyderabadi":   ["Dum Biryani", "Haleem", "Mirchi Ka Salan"],
    "bakery":       ["Egg Puff", "Cake Slice", "Osmania Biscuit"],
    "cafe":         ["Cold Brew", "Sandwich", "Pasta", "Latte"],
    "dessert":      ["Brownie Sundae", "Tiramisu", "Waffle"],
    "ice_cream":    ["Sundae", "Single Scoop", "Milkshake"],
    "fast_food":    ["Zinger Burger", "Fries", "Wrap", "Combo Meal"],
    "pizza":        ["Margherita", "Pepperoni", "BBQ Chicken Pizza"],
    "street_food":  ["Pani Puri", "Bhel Puri", "Papdi Chaat"],
    "south_indian": ["Masala Dosa", "Idli Sambar", "Uttapam"],
}


def get_craving_keywords(craving):
    craving = craving.lower().strip()
    for key, exp in CRAVING_EXPAND.items():
        if craving == key or craving in key or key in craving:
            return exp
    return [craving]


def matches_craving(blob, keywords):
    if not keywords:
        return True
    return any(kw in blob for kw in keywords)


def pick_dishes(name, blob):
    for key, dishes in DISH_MAP.items():
        if key in blob:
            return dishes[abs(hash(name)) % len(dishes)]
    return "Chef's Special"


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)


def eta_from_distance(dist_km):
    """Estimate ETA in minutes (assuming 20 km/h in city traffic + 2 min base)."""
    return round((dist_km / 20) * 60 + 2)


def fetch_osm_places(lat, lng, craving, radius=4000):
    results, seen = [], set()
    amenity_union = "\n".join(
        f'  node["amenity"="{a}"](around:{radius},{lat},{lng});\n'
        f'  way["amenity"="{a}"](around:{radius},{lat},{lng});'
        for a in OSM_AMENITY_TAGS
    )
    query = f"[out:json][timeout:15];\n(\n{amenity_union}\n);\nout center 100;\n"
    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query}, timeout=18,
            headers={"User-Agent": "TelanganaFoodGenie/2.0"}
        )
        for el in resp.json().get("elements", []):
            tags = el.get("tags", {})
            name = (tags.get("name") or tags.get("name:en") or "").strip()
            if not name or name.lower() in seen:
                continue
            p_lat = el.get("lat") or el.get("center", {}).get("lat")
            p_lng = el.get("lon") or el.get("center", {}).get("lon")
            if not p_lat or not p_lng:
                continue
            search_dist = calculate_distance(lat, lng, p_lat, p_lng)
            if search_dist > radius / 1000:
                continue
            amenity = tags.get("amenity", "restaurant")
            cuisine = tags.get("cuisine", craving or amenity).replace("_", " ").capitalize()
            if craving and craving != "all":
                keywords = get_craving_keywords(craving)
                blob = (name + " " + cuisine + " " + amenity + " " + tags.get("cuisine", "")).lower()
                if not matches_craving(blob, keywords):
                    continue
            seen.add(name.lower())
            blob = (name + " " + cuisine + " " + amenity).lower()
            osm_stars = tags.get("stars") or tags.get("rating")
            try:
                hygiene = f"{float(osm_stars):.1f}/5" if osm_stars else f"{round(3.5 + (abs(hash(name)) % 15) / 10, 1)}/5"
            except Exception:
                hygiene = f"{round(3.5 + (abs(hash(name)) % 15) / 10, 1)}/5"
            diet = "veg" if tags.get("diet:vegetarian") in ("yes", "only") else "both"
            # distance/eta NOT set here — recalculated from user GPS in /recommend route
            results.append({
                "name":          name,
                "type":          amenity.replace("_", " ").capitalize(),
                "cuisine":       cuisine,
                "lat":           p_lat,
                "lng":           p_lng,
                "hygiene":       hygiene,
                "diet":          diet,
                "dishes":        pick_dishes(name, blob),
                "saved_reviews": get_reviews(name)
            })
    except Exception as e:
        print(f"[OSM] Error: {e}")
    return results


def geocode_address(addr):
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": addr + ", Telangana, India", "format": "json", "limit": 1},
            timeout=8, headers={"User-Agent": "TelanganaFoodGenie/2.0"}
        )
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"[Nominatim] {e}")
    return None


# ─────────────────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    return render_template('index.html', user=current_user.email)


@app.route('/recommend', methods=['POST'])
@login_required
def recommend():
    craving     = request.form.get('craving', '').lower().strip()
    diet_pref   = request.form.get('diet', 'all').lower().strip()
    # Treat "all" keyword same as empty craving
    if craving == 'all':
        craving = ''
    loc_mode    = request.form.get('location_mode')

    # u_lat/u_lng  = user's actual GPS (always used for distance/ETA)
    # s_lat/s_lng  = search centre (where to fetch restaurants from)
    u_lat, u_lng = 17.3850, 78.4867   # fallback: Hyderabad Central
    try:
        gps_lat = float(request.form.get('lat') or 0)
        gps_lng = float(request.form.get('lng') or 0)
        if gps_lat and gps_lng:
            u_lat, u_lng = gps_lat, gps_lng
    except Exception:
        pass

    if loc_mode == 'manual':
        addr   = request.form.get('manual_address', '')
        coords = geocode_address(addr)
        if coords:
            s_lat, s_lng, loc_label = coords[0], coords[1], addr
        else:
            s_lat, s_lng, loc_label = u_lat, u_lng, "Your Location"
    else:
        s_lat, s_lng, loc_label = u_lat, u_lng, "Your Location"

    keywords   = get_craving_keywords(craving) if craving else []
    all_results, seen_names = [], set()

    for r in CORE_DATA:
        # Filter/fetch based on search centre; distance shown from user's GPS
        if diet_pref == 'veg'    and r.get('diet') not in ('veg',):    continue
        if diet_pref == 'nonveg' and r.get('diet') not in ('nonveg', 'both'): continue
        blob = (r['name'] + " " + r['cuisine'] + " " + r['type'] + " " + r['dishes']).lower()
        if not craving or craving == "all" or matches_craving(blob, keywords):
            res = r.copy()
            dist = calculate_distance(u_lat, u_lng, r['lat'], r['lng'])
            res.update({
                "distance":      dist,
                "eta":           eta_from_distance(dist),
                "saved_reviews": get_reviews(r['name'])
            })
            all_results.append(res)
            seen_names.add(r['name'].lower())

    for place in fetch_osm_places(s_lat, s_lng, craving):
        if place['name'].lower() not in seen_names:
            if diet_pref == 'veg'    and place.get('diet') not in ('veg',): continue
            if diet_pref == 'nonveg' and place.get('diet') not in ('nonveg', 'both'): continue
            # Distance/ETA always from user's real GPS, not the searched location
            dist = calculate_distance(u_lat, u_lng, place['lat'], place['lng'])
            place['distance'] = dist
            place['eta']      = eta_from_distance(dist)
            all_results.append(place)
            seen_names.add(place['name'].lower())

    all_results = sorted(all_results, key=lambda x: x['distance'])
    return render_template(
        'index.html',
        results     = all_results,
        craving     = craving,
        diet_pref   = diet_pref,
        user        = current_user.email,
        loc_label   = loc_label,
        no_results  = (len(all_results) == 0)
    )


@app.route('/add_review', methods=['POST'])
@login_required
def add_review():
    try:
        stars = max(1, min(5, int(request.form.get('star_rating', 5))))
    except (ValueError, TypeError):
        stars = 5

    is_verified = False
    try:
        u_lat = float(request.form.get('user_lat', 0))
        u_lng = float(request.form.get('user_lng', 0))
        r_lat = float(request.form.get('rest_lat', 0))
        r_lng = float(request.form.get('rest_lng', 0))
        if all([u_lat, u_lng, r_lat, r_lng]):
            is_verified = calculate_distance(u_lat, u_lng, r_lat, r_lng) <= 1.0
    except (ValueError, TypeError):
        pass

    add_review_db(
        restaurant_name = request.form.get('restaurant_name'),
        user_email      = current_user.email,
        comment         = request.form.get('comment', '').strip(),
        stars           = stars,
        is_verified     = is_verified
    )
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        # Basic validation
        if not email or not password:
            flash("Email and password are required.")
            return render_template('register.html')
        if len(password) < 8:
            flash("Password must be at least 8 characters.")
            return render_template('register.html')
        if get_user_by_email(email):
            flash("An account with that email already exists.")
            return render_template('register.html')

        hashed = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)
        create_user(email, hashed)
        flash("Account created! Please log in.")
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user     = get_user_by_email(email)

        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            return redirect(url_for('index'))
        flash("Invalid email or password.")
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


if __name__ == '__main__':
    if not USE_MONGO:
        with app.app_context():
            db.create_all()
    app.run(debug=False)  # Never run debug=True in production