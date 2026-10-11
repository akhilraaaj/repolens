from app.answers.compose import compose_answer
from app.answers.validate import renumber, validate_answer


def test_citation_markers_follow_the_cited_list() -> None:
    text, used, abstained = validate_answer("It widens literals [2]. Tests cover it [3]. Not a guard [4]. Bogus [9].", 4)
    assert abstained is False
    assert used == [2, 3, 4]
    assert renumber(text, used) == "It widens literals [1]. Tests cover it [2]. Not a guard [3]. Bogus ."

FIREBASE = """import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
export const auth = getAuth(app);
"""

LOGIN = """import { useSignInWithEmailAndPassword, useSignInWithGoogle } from 'react-firebase-hooks/auth';
import { auth } from '../common/firebase';
import { useNavigate } from 'react-router-dom';

export default function Login() {
    const [ signInWithEmailAndPassword, user] = useSignInWithEmailAndPassword(auth);
    const [ signInWithGoogle, gUser ] = useSignInWithGoogle(auth);
"""


def test_auth_question_names_the_imported_packages() -> None:
    answer = compose_answer(
        "what is used for auth?",
        [
            {
                "path": "src/common/firebase.js",
                "start_line": 20,
                "end_line": 20,
                "snippet": "export const auth = getAuth(app);",
            },
            {
                "path": "src/components/Login.jsx",
                "start_line": 10,
                "end_line": 16,
                "snippet": LOGIN,
            },
        ],
        {
            "src/common/firebase.js": FIREBASE,
            "src/components/Login.jsx": LOGIN,
        },
    )

    assert answer.startswith("This commit uses ")
    assert "firebase/auth, through getAuth" in answer
    assert "react-firebase-hooks/auth" in answer
    assert "useSignInWithEmailAndPassword" in answer
    assert "react-router-dom" not in answer
    assert "\n" not in answer


def test_return_question_quotes_the_return_expression() -> None:
    snippet = "export function add(left: number, right: number): number {\n  return left + right;\n}\n"
    answer = compose_answer(
        "What does add return?",
        [{"path": "src/math.ts", "start_line": 1, "end_line": 3, "snippet": snippet}],
        {"src/math.ts": snippet},
    )

    assert answer.startswith("add returns left + right. That is in src/math.ts.")
    assert "payment" not in answer.lower()
