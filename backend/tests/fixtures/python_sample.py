"""Python fixture source used by parser tests — no imports needed."""

PYTHON_SOURCE = '''\
def authenticate_user(username: str, password: str):
    """Authenticate a user and return a JWT."""
    hashed = hash_password(password)
    user = db.query(User).filter(User.username == username).first()
    if user and user.password_hash == hashed:
        return generate_token(user.id)
    return None


class UserService:
    def __init__(self, db_session):
        self.db = db_session

    def get_user(self, user_id: int):
        return self.db.query(User).filter(User.id == user_id).first()

    def create_user(self, username: str, email: str):
        user = User(username=username, email=email)
        self.db.add(user)
        self.db.commit()
        return user
'''

TYPESCRIPT_SOURCE = """\
async function fetchUser(userId: string): Promise<User | null> {
  const user = await db.users.findUnique({ where: { id: userId } });
  return user;
}

class AuthService {
  constructor(private readonly db: Database) {}

  async login(email: string, password: string): Promise<string> {
    const user = await this.db.users.findFirst({ where: { email } });
    if (!user) throw new Error("User not found");
    return generateToken(user.id);
  }
}
"""

PYTHON_PATCH = """\
@@ -1,6 +1,6 @@
 def authenticate_user(username: str, password: str):
     \"\"\"Authenticate a user and return a JWT.\"\"\"
-    hashed = hash_password(password)
+    user_id = request.args.get('id')   # type: ignore
     user = db.query(User).filter(User.username == username).first()
-    if user and user.password_hash == hashed:
+    if user:
         return generate_token(user.id)
"""
