from app import db
from models import User
from werkzeug.security import generate_password_hash

if not User.query.filter_by(email="test@example.com").first():
    test_user = User(
        first_name="dev"
        last_name="test"
        display_name="test_dev"
        email="test@example.com",
        password_hash=generate_password_hash("test123"),
        agreed_to_terms=True
        age_confirmed=True
    )
    db.session.add(test_user)
    db.session.commit()
    print("✅ Test user created.")