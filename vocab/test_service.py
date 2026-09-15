"""
Vocabulary Test Service and Benchmark Engine.

Integrates:
- OpenTDB API for general books & vocabulary multiple-choice questions
- Datamuse API for synonym and contextual semantic drills
- Comprehensive offline CEFR benchmark question bank (A1 to C2) for guaranteed offline resilience
- Adaptive proficiency scoring and active vocabulary size estimation
"""
from __future__ import annotations
import json
import html
import random
import urllib.request
import urllib.parse
import urllib.error
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple


@dataclass
class TestQuestion:
    __test__ = False  # Prevent pytest from attempting to collect TestQuestion as a test suite
    prompt: str
    choices: List[str]
    correct_index: int  # 0 to 3
    explanation: str = ""
    difficulty: str = "medium"  # "easy", "medium", "hard" or CEFR level
    category: str = "Vocabulary"
    word: str = ""
    cefr_level: str = "B1"

    @property
    def correct_answer(self) -> str:
        if 0 <= self.correct_index < len(self.choices):
            return self.choices[self.correct_index]
        return ""


CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]

# Incremental frequency band sizes based on Cambridge English Profile & Paul Nation's vocabulary levels:
# A1: ~1,500 core everyday words
# A2: +1,500 basic descriptive words (cumulative 3,000)
# B1: +2,500 intermediate conversational & text words (cumulative 5,500)
# B2: +4,000 upper-intermediate academic & abstract words (cumulative 9,500)
# C1: +6,500 advanced literary & technical words (cumulative 16,000)
# C2: +9,000 erudite, GRE/SAT & mastery words (cumulative 25,000)
TIER_BAND_WORDS = {
    "A1": 1500,
    "A2": 1500,
    "B1": 2500,
    "B2": 4000,
    "C1": 6500,
    "C2": 9000,
}

CEFR_VOCAB_THRESHOLDS = [
    ("A1", 1800),
    ("A2", 3500),
    ("B1", 6500),
    ("B2", 11500),
    ("C1", 18500),
    ("C2", 26000),
]

CEFR_WEIGHTS = {
    "A1": 1.0,
    "A2": 2.0,
    "B1": 3.0,
    "B2": 4.0,
    "C1": 5.0,
    "C2": 6.0,
}



# --- High-Quality Leveled Benchmark Item Bank (CEFR A1 to C2) ---

BENCHMARK_QUESTION_BANK: List[Dict[str, Any]] = [
    # === A1: Beginner (High Frequency Fundamentals) ===
    {
        "word": "ancient",
        "cefr_level": "A1",
        "difficulty": "easy",
        "category": "Antonyms & Synonyms",
        "prompt": "What is the closest synonym for 'ancient'?",
        "choices": ["very old", "modern", "dangerous", "tiny"],
        "correct_index": 0,
        "explanation": "'Ancient' means belonging to the very distant past and no longer in existence, or extremely old."
    },
    {
        "word": "cautious",
        "cefr_level": "A1",
        "difficulty": "easy",
        "category": "Word Meaning",
        "prompt": "Someone who is 'cautious' is:",
        "choices": ["Angry and impatient", "Careful to avoid problems or danger", "Extremely loud", "Always cheerful"],
        "correct_index": 1,
        "explanation": "'Cautious' means alert to potential dangers, risks, or mistakes."
    },
    {
        "word": "frequent",
        "cefr_level": "A1",
        "difficulty": "easy",
        "category": "Sentence Completion",
        "prompt": "Trains between the two cities are very _______, departing every ten minutes.",
        "choices": ["frequent", "reluctant", "fragile", "distant"],
        "correct_index": 0,
        "explanation": "'Frequent' means occurring or appearing at short intervals."
    },
    {
        "word": "delight",
        "cefr_level": "A1",
        "difficulty": "easy",
        "category": "Word Meaning",
        "prompt": "Which word means great pleasure or satisfaction?",
        "choices": ["Sorrow", "Delight", "Despair", "Tension"],
        "correct_index": 1,
        "explanation": "'Delight' denotes high pleasure, enjoyment, or satisfaction."
    },
    {
        "word": "permit",
        "cefr_level": "A1",
        "difficulty": "easy",
        "category": "Antonyms & Synonyms",
        "prompt": "What is the best synonym for 'permit'?",
        "choices": ["Allow", "Forbid", "Destroy", "Escape"],
        "correct_index": 0,
        "explanation": "'To permit' means to give authorization or allow something to happen."
    },
    {
        "word": "journey",
        "cefr_level": "A1",
        "difficulty": "easy",
        "category": "Word Meaning",
        "prompt": "An act of traveling from one place to another is called a:",
        "choices": ["Dispute", "Journey", "Verdict", "Summit"],
        "correct_index": 1,
        "explanation": "A 'journey' is an act of traveling from one destination to another."
    },

    # === A2: Elementary (Everyday Academic & Descriptive) ===
    {
        "word": "accurate",
        "cefr_level": "A2",
        "difficulty": "easy",
        "category": "Word Meaning",
        "prompt": "If a measurement or report is 'accurate', it is:",
        "choices": ["Roughly estimated", "Correct in all details and exact", "Fictional and made up", "Outdated"],
        "correct_index": 1,
        "explanation": "'Accurate' means conforming strictly to fact or a standard; correct in all details."
    },
    {
        "word": "hesitate",
        "cefr_level": "A2",
        "difficulty": "easy",
        "category": "Sentence Completion",
        "prompt": "Do not _______ to contact our support team if you encounter any difficulties.",
        "choices": ["hesitate", "conquer", "demolish", "resemble"],
        "correct_index": 0,
        "explanation": "'Hesitate' means to pause before saying or doing something, often due to doubt or reluctance."
    },
    {
        "word": "essential",
        "cefr_level": "A2",
        "difficulty": "easy",
        "category": "Synonyms",
        "prompt": "Which word is a synonym for 'essential'?",
        "choices": ["Optional", "Crucial", "Decorative", "Minor"],
        "correct_index": 1,
        "explanation": "'Essential' means absolutely necessary or extremely important; crucial."
    },
    {
        "word": "conclude",
        "cefr_level": "A2",
        "difficulty": "easy",
        "category": "Word Meaning",
        "prompt": "To 'conclude' a meeting or essay means to:",
        "choices": ["Bring it to an end or finish it", "Postpone it indefinitely", "Argue loudly about it", "Begin it abruptly"],
        "correct_index": 0,
        "explanation": "'Conclude' means to bring something to an end or arrive at an opinion/judgement."
    },
    {
        "word": "benefit",
        "cefr_level": "A2",
        "difficulty": "easy",
        "category": "Synonyms",
        "prompt": "An advantage or positive profit gained from something is a:",
        "choices": ["Detriment", "Benefit", "Hazard", "Disadvantage"],
        "correct_index": 1,
        "explanation": "A 'benefit' is an advantageous or helpful outcome."
    },
    {
        "word": "gradual",
        "cefr_level": "A2",
        "difficulty": "easy",
        "category": "Sentence Completion",
        "prompt": "Over the past decade, we have seen a _______ change in global temperatures.",
        "choices": ["gradual", "hasty", "sudden", "negligent"],
        "correct_index": 0,
        "explanation": "'Gradual' describes taking place or progressing slowly or by degrees."
    },

    # === B1: Intermediate (Expanding Lexicon & Idiomatic Fluency) ===
    {
        "word": "benevolent",
        "cefr_level": "B1",
        "difficulty": "medium",
        "category": "Word Meaning",
        "prompt": "A 'benevolent' leader or donor is characterized by:",
        "choices": ["Selfishness and arrogance", "Cruelty and spite", "Kindness, goodwill, and charitable intentions", "Indifference and silence"],
        "correct_index": 2,
        "explanation": "'Benevolent' originates from Latin 'bene' (well) + 'velle' (to wish), meaning kindly and generous."
    },
    {
        "word": "tedious",
        "cefr_level": "B1",
        "difficulty": "medium",
        "category": "Synonyms",
        "prompt": "Which word is closest in meaning to 'tedious'?",
        "choices": ["Monotonous and boring", "Thrilling and captivating", "Complicated and deep", "Rapid and swift"],
        "correct_index": 0,
        "explanation": "'Tedious' means too long, slow, or dull; tiresome or monotonous."
    },
    {
        "word": "ambiguous",
        "cefr_level": "B1",
        "difficulty": "medium",
        "category": "Word Meaning",
        "prompt": "If instructions or answers are 'ambiguous', they are:",
        "choices": ["Completely crystalline and obvious", "Open to more than one interpretation; unclear", "Strictly prohibited", "Very entertaining"],
        "correct_index": 1,
        "explanation": "'Ambiguous' means capable of being understood in two or more possible senses or ways."
    },
    {
        "word": "resilient",
        "cefr_level": "B1",
        "difficulty": "medium",
        "category": "Sentence Completion",
        "prompt": "The local community proved remarkably _______, rapidly recovering after the severe winter storm.",
        "choices": ["resilient", "fragile", "indolent", "hostile"],
        "correct_index": 0,
        "explanation": "'Resilient' denotes the capacity to recover quickly from difficulties, adversity, or damage."
    },
    {
        "word": "plausible",
        "cefr_level": "B1",
        "difficulty": "medium",
        "category": "Word Meaning",
        "prompt": "An explanation that is 'plausible' is one that:",
        "choices": ["Is completely impossible", "Sounds reasonable and likely to be true", "Is guaranteed to be false", "Causes loud laughter"],
        "correct_index": 1,
        "explanation": "'Plausible' means having an appearance of truth or reason; seemingly valid or acceptable."
    },
    {
        "word": "vigilant",
        "cefr_level": "B1",
        "difficulty": "medium",
        "category": "Synonyms",
        "prompt": "A security officer who remains 'vigilant' is:",
        "choices": ["Watchful and alert for danger", "Asleep on duty", "Extremely careless", "Combative and aggressive"],
        "correct_index": 0,
        "explanation": "'Vigilant' means keeping careful watch for possible dangers or difficulties."
    },

    # === B2: Upper-Intermediate (Abstract Concepts & Professional Nuance) ===
    {
        "word": "pragmatic",
        "cefr_level": "B2",
        "difficulty": "medium",
        "category": "Word Meaning",
        "prompt": "A 'pragmatic' approach to solving a business problem focuses on:",
        "choices": ["Abstract theoretical ideals", "Practical results and realistic considerations", "Historical traditions only", "Blind luck"],
        "correct_index": 1,
        "explanation": "'Pragmatic' means dealing with things sensibly and realistically based on practical rather than theoretical considerations."
    },
    {
        "word": "ubiquitous",
        "cefr_level": "B2",
        "difficulty": "medium",
        "category": "Synonyms",
        "prompt": "Smartphones have become 'ubiquitous' in modern society. 'Ubiquitous' means:",
        "choices": ["Omnipresent / found everywhere", "Rare and difficult to acquire", "Extremely fragile", "Prohibitively expensive"],
        "correct_index": 0,
        "explanation": "'Ubiquitous' means present, appearing, or found everywhere simultaneously."
    },
    {
        "word": "mitigate",
        "cefr_level": "B2",
        "difficulty": "medium",
        "category": "Sentence Completion",
        "prompt": "Emergency services took precautions to _______ the impact of the impending flood.",
        "choices": ["mitigate", "exacerbate", "instigate", "provoke"],
        "correct_index": 0,
        "explanation": "'Mitigate' means to make something less severe, serious, or painful."
    },
    {
        "word": "tenacious",
        "cefr_level": "B2",
        "difficulty": "medium",
        "category": "Word Meaning",
        "prompt": "A scientist described as 'tenacious' is one who:",
        "choices": ["Gives up at the first hurdle", "Persists with firm determination and perseverance", "Frequently switches topics", "Refuses to collaborate"],
        "correct_index": 1,
        "explanation": "'Tenacious' means holding firmly to a purpose, goal, or belief; stubborn persistence."
    },
    {
        "word": "scrutinize",
        "cefr_level": "B2",
        "difficulty": "medium",
        "category": "Synonyms",
        "prompt": "To 'scrutinize' financial records means to:",
        "choices": ["Glance at them casually", "Examine or inspect them closely and thoroughly", "Shred or destroy them", "Hide them from auditors"],
        "correct_index": 1,
        "explanation": "'Scrutinize' means to examine or inspect closely and thoroughly with critical scrutiny."
    },
    {
        "word": "lucid",
        "cefr_level": "B2",
        "difficulty": "medium",
        "category": "Word Meaning",
        "prompt": "If a philosopher gives a 'lucid' lecture, it is:",
        "choices": ["Extremely clear and easy to understand", "Murky, obscure, and rambling", "Filled with technical jargon", "Sleep-inducing"],
        "correct_index": 0,
        "explanation": "'Lucid' means expressed clearly, easy to understand, or having clear mental faculties."
    },

    # === C1: Advanced (Nuanced, Sophisticated, Academic Literature) ===
    {
        "word": "ephemeral",
        "cefr_level": "C1",
        "difficulty": "hard",
        "category": "Word Meaning",
        "prompt": "Something that is 'ephemeral' is:",
        "choices": ["Eternal and permanent", "Fleeting, transient, lasting a very short time", "Heavily ornamented", "Poisonous"],
        "correct_index": 1,
        "explanation": "'Ephemeral' (from Greek ephēmeros) describes anything that lasts only for a day or a brief fleeting period."
    },
    {
        "word": "cacophony",
        "cefr_level": "C1",
        "difficulty": "hard",
        "category": "Synonyms",
        "prompt": "The construction site generated a deafening 'cacophony'. 'Cacophony' means:",
        "choices": ["A harsh, discordant mixture of sounds", "A gentle harmonious melody", "A complete silence", "A rhythmic chant"],
        "correct_index": 0,
        "explanation": "'Cacophony' is a harsh, discordant, jarring mixture of sounds."
    },
    {
        "word": "fastidious",
        "cefr_level": "C1",
        "difficulty": "hard",
        "category": "Word Meaning",
        "prompt": "An editor with 'fastidious' attention to detail is:",
        "choices": ["Very attentive to and concerned about accuracy and detail; meticulous", "Rushed and sloppy", "Indifferent to typographical errors", "Slow and sluggish"],
        "correct_index": 0,
        "explanation": "'Fastidious' means very attentive to and concerned about accuracy, order, and cleanliness; excessively particular."
    },
    {
        "word": "alacrity",
        "cefr_level": "C1",
        "difficulty": "hard",
        "category": "Sentence Completion",
        "prompt": "Eager for the assignment, she accepted the promotion with _______ and enthusiasm.",
        "choices": ["alacrity", "lethargy", "reluctance", "resentment"],
        "correct_index": 0,
        "explanation": "'Alacrity' signifies brisk and cheerful readiness, promptness, or willingness."
    },
    {
        "word": "quintessential",
        "cefr_level": "C1",
        "difficulty": "hard",
        "category": "Word Meaning",
        "prompt": "If a restaurant is described as the 'quintessential' Parisian bistro, it represents:",
        "choices": ["The absolute worst example", "The most perfect, typical, or representative embodiment", "A foreign imitation", "A futuristic rendition"],
        "correct_index": 1,
        "explanation": "'Quintessential' means representing the most perfect or typical example of a quality or class."
    },
    {
        "word": "superfluous",
        "cefr_level": "C1",
        "difficulty": "hard",
        "category": "Synonyms",
        "prompt": "Which word is a synonym for 'superfluous'?",
        "choices": ["Indispensable", "Redundant / excess", "Deficient", "Concise"],
        "correct_index": 1,
        "explanation": "'Superfluous' means exceeding what is sufficient or necessary; unnecessary or redundant."
    },

    # === C2: Mastery (Erudite, GRE/SAT High-Difficulty, Stylistic Mastery) ===
    {
        "word": "perspicacious",
        "cefr_level": "C2",
        "difficulty": "hard",
        "category": "Word Meaning",
        "prompt": "A 'perspicacious' analyst or critic possesses:",
        "choices": ["Blurry vision", "Keen insight, mental penetration, and shrewd discerning power", "Superficial knowledge", "A stubborn prejudice"],
        "correct_index": 1,
        "explanation": "'Perspicacious' (Latin perspicax) means having keen mental discernment; perceptive, shrewd."
    },
    {
        "word": "anachronistic",
        "cefr_level": "C2",
        "difficulty": "hard",
        "category": "Word Meaning",
        "prompt": "Depicting a wristwatch in a film set in ancient Rome is:",
        "choices": ["Anachronistic", "Prescient", "Philanthropic", "Aesthetic"],
        "correct_index": 0,
        "explanation": "'Anachronistic' means belonging or appropriate to a period other than that in which it exists; chronologically misplaced."
    },
    {
        "word": "surreptitious",
        "cefr_level": "C2",
        "difficulty": "hard",
        "category": "Synonyms",
        "prompt": "Which word is closest in meaning to 'surreptitious'?",
        "choices": ["Clandestine / secret", "Blatant / overt", "Magnanimous", "Lilliputian"],
        "correct_index": 0,
        "explanation": "'Surreptitious' means kept secret, especially because it would not be approved of; stealthy."
    },
    {
        "word": "pusillanimous",
        "cefr_level": "C2",
        "difficulty": "hard",
        "category": "Word Meaning",
        "prompt": "Someone who is 'pusillanimous' demonstrates:",
        "choices": ["Audacious bravery", "Timid cowardice and a lack of courage", "Philosophical wisdom", "Generous hospitality"],
        "correct_index": 1,
        "explanation": "'Pusillanimous' (Latin pusillus 'very small' + animus 'mind/spirit') means showing a lack of courage or determination; timid."
    },
    {
        "word": "enervate",
        "cefr_level": "C2",
        "difficulty": "hard",
        "category": "Antonyms & Synonyms",
        "prompt": "To 'enervate' someone means to:",
        "choices": ["Energize and invigorate them", "Drain of energy, weaken, or exhaust them", "Enrage them deeply", "Congratulate them warmly"],
        "correct_index": 1,
        "explanation": "'Enervate' means to cause someone to feel drained of energy or vitality; weaken. (Often mistaken for 'energize')."
    },
    {
        "word": "chicanery",
        "cefr_level": "C2",
        "difficulty": "hard",
        "category": "Word Meaning",
        "prompt": "In legal or political contexts, 'chicanery' refers to:",
        "choices": ["Transparent honesty", "The use of trickery, deceit, or subterfuge to achieve a goal", "Public celebration", "Incompetence without intent"],
        "correct_index": 1,
        "explanation": "'Chicanery' denotes clever, devious trickery or deception used in speech, law, or politics."
    },
    {
        "word": "perfunctory",
        "cefr_level": "C2",
        "difficulty": "hard",
        "category": "Sentence Completion",
        "prompt": "The tired guard gave only a _______ inspection of our passports before waving us through.",
        "choices": ["perfunctory", "scrupulous", "meticulous", "comprehensive"],
        "correct_index": 0,
        "explanation": "'Perfunctory' means carried out with a minimum of effort, routine reflection, or interest."
    },
    {
        "word": "obsequious",
        "cefr_level": "C2",
        "difficulty": "hard",
        "category": "Word Meaning",
        "prompt": "An 'obsequious' subordinate is one who is:",
        "choices": ["Excessively obedient, servile, and fawning to gain favor", "Rebellious and confrontational", "Quietly competent and dignified", "Aloof and detached"],
        "correct_index": 0,
        "explanation": "'Obsequious' describes someone obedient or attentive to an excessive or servile degree; sycophantic."
    }
]


class VocabTestService:
    """
    Central test service orchestrating OpenTDB, Datamuse, and offline benchmark question banks.
    """

    @classmethod
    def fetch_opentdb_questions(
        cls,
        amount: int = 10,
        difficulty: Optional[str] = None,
        timeout: float = 2.5
    ) -> List[TestQuestion]:
        """
        Fetches questions from OpenTDB (Category 10: Entertainment - Books & Literature / Words).
        If network times out or fails, falls back gracefully to the offline benchmark bank.
        """
        url = f"https://opentdb.com/api.php?amount={min(amount, 20)}&category=10&type=multiple"
        if difficulty in ("easy", "medium", "hard"):
            url += f"&difficulty={difficulty}"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "VocabTerminalApp/2.0 (Language Learning Tools)"}
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("response_code") == 0 and data.get("results"):
                questions: List[TestQuestion] = []
                for item in data["results"]:
                    q_text = html.unescape(item.get("question", ""))
                    correct = html.unescape(item.get("correct_answer", ""))
                    incorrects = [html.unescape(ans) for ans in item.get("incorrect_answers", [])]

                    diff = item.get("difficulty", "medium")
                    cefr = "A2" if diff == "easy" else ("B2" if diff == "medium" else "C1")

                    choices = incorrects + [correct]
                    random.shuffle(choices)
                    c_idx = choices.index(correct)

                    questions.append(
                        TestQuestion(
                            prompt=q_text,
                            choices=choices,
                            correct_index=c_idx,
                            explanation=f"Correct answer: '{correct}'",
                            difficulty=diff,
                            category="Literature & Vocabulary (OpenTDB)",
                            word=correct,
                            cefr_level=cefr
                        )
                    )

                if len(questions) >= amount:
                    return questions[:amount]
                # If OpenTDB returned fewer questions than requested, supplement from bank
                needed = amount - len(questions)
                supplement = cls.get_leveled_benchmark_questions(amount=needed)
                return questions + supplement

        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError, Exception):
            # Graceful seamless fallback to built-in benchmark bank
            pass

        return cls.get_leveled_benchmark_questions(amount=amount)

    @classmethod
    def fetch_datamuse_questions(
        cls,
        amount: int = 10,
        timeout: float = 2.5
    ) -> List[TestQuestion]:
        """
        Generates synonym and contextual questions via Datamuse API.
        Falls back seamlessly to the built-in benchmark bank if offline.
        """
        target_words = [
            ("pragmatic", "practical", "B2"),
            ("lucid", "clear", "B2"),
            ("ephemeral", "fleeting", "C1"),
            ("alacrity", "eagerness", "C1"),
            ("resilient", "tough", "B1"),
            ("tenacious", "persistent", "B2"),
            ("surreptitious", "secret", "C2"),
            ("benevolent", "kind", "B1"),
            ("accurate", "correct", "A2"),
            ("ancient", "old", "A1"),
            ("vigilant", "watchful", "B1"),
            ("tedious", "boring", "B1"),
        ]
        random.shuffle(target_words)
        selected_targets = target_words[:amount]

        questions: List[TestQuestion] = []

        try:
            for word, fallback_syn, cefr in selected_targets:
                encoded = urllib.parse.quote(word)
                url = f"https://api.datamuse.com/words?rel_syn={encoded}&max=5"
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "VocabTerminalApp/2.0"}
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    syn_data = json.loads(resp.read().decode("utf-8"))

                correct_syn = syn_data[0]["word"] if syn_data else fallback_syn

                # Fetch distractors
                distractor_candidates = [
                    w for w, _, _ in target_words if w != word and w != correct_syn
                ]
                distractors = random.sample(distractor_candidates, min(3, len(distractor_candidates)))
                while len(distractors) < 3:
                    distractors.append("unrelated")

                choices = distractors + [correct_syn]
                random.shuffle(choices)
                c_idx = choices.index(correct_syn)

                questions.append(
                    TestQuestion(
                        prompt=f"Which word is the closest synonym for '{word}'?",
                        choices=choices,
                        correct_index=c_idx,
                        explanation=f"'{correct_syn}' is a direct synonym for '{word}'.",
                        difficulty="medium",
                        category="Synonym Challenge (Datamuse)",
                        word=word,
                        cefr_level=cefr
                    )
                )

            if len(questions) >= amount:
                return questions[:amount]

        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, Exception):
            pass

        # Fallback to benchmark questions
        return cls.get_leveled_benchmark_questions(amount=amount)

    @classmethod
    def get_leveled_benchmark_questions(
        cls,
        amount: int = 12,
        level: Optional[str] = None
    ) -> List[TestQuestion]:
        """
        Retrieves benchmark questions.
        If level is None, creates a balanced progressive staircase across A1 -> C2.
        """
        if level:
            candidates = [q for q in BENCHMARK_QUESTION_BANK if q["cefr_level"] == level.upper()]
            if not candidates:
                candidates = BENCHMARK_QUESTION_BANK
            random.shuffle(candidates)
            selected = candidates[:amount]
        else:
            # Progressive staircase: pull evenly from A1, A2, B1, B2, C1, C2
            tiers = ["A1", "A2", "B1", "B2", "C1", "C2"]
            per_tier = max(1, amount // len(tiers))
            selected: List[Dict[str, Any]] = []

            for tier in tiers:
                tier_pool = [q for q in BENCHMARK_QUESTION_BANK if q["cefr_level"] == tier]
                random.shuffle(tier_pool)
                selected.extend(tier_pool[:per_tier])

            # If still need more to hit requested amount
            if len(selected) < amount:
                remaining_pool = [q for q in BENCHMARK_QUESTION_BANK if q not in selected]
                random.shuffle(remaining_pool)
                selected.extend(remaining_pool[: amount - len(selected)])

            # Staircase progression: sort by CEFR order
            tier_order = {t: i for i, t in enumerate(tiers)}
            selected.sort(key=lambda item: tier_order.get(item.get("cefr_level", "B1"), 2))

        result: List[TestQuestion] = []
        for raw in selected[:amount]:
            result.append(
                TestQuestion(
                    prompt=raw["prompt"],
                    choices=list(raw["choices"]),
                    correct_index=raw["correct_index"],
                    explanation=raw.get("explanation", ""),
                    difficulty=raw.get("difficulty", "medium"),
                    category=raw.get("category", "CEFR Benchmark"),
                    word=raw.get("word", ""),
                    cefr_level=raw.get("cefr_level", "B1")
                )
            )
        return result

    @classmethod
    def estimate_proficiency(
        cls,
        questions: List[TestQuestion],
        user_correct: List[bool],
        avg_response_time: float = 0.0
    ) -> Dict[str, Any]:
        """
        Calculates CEFR proficiency level, estimated English vocabulary size,
        and qualitative analysis from test performance with strict psychometric validity.
        """
        if not questions:
            return {
                "score_pct": 0.0,
                "weighted_pct": 0.0,
                "correct_count": 0,
                "total_questions": 0,
                "cefr_level": "A1",
                "cefr_label": "A1 - Beginner (Foundation)",
                "estimated_vocab_size": 800,
                "speed_rating": "Untimed",
                "feedback": "No questions answered.",
                "level_breakdown": {},
                "is_reliable": False,
                "sample_warning": "No questions answered."
            }

        total = len(questions)
        correct_count = sum(1 for c in user_correct if c)
        raw_pct = (correct_count / total) * 100.0

        # Group performance by CEFR tier
        level_stats: Dict[str, Dict[str, int]] = {
            tier: {"correct": 0, "total": 0} for tier in CEFR_LEVELS
        }
        for q, is_corr in zip(questions, user_correct):
            tier = q.cefr_level.upper() if q.cefr_level and q.cefr_level.upper() in level_stats else "B1"
            level_stats[tier]["total"] += 1
            if is_corr:
                level_stats[tier]["correct"] += 1

        tested_tiers = [t for t in CEFR_LEVELS if level_stats[t]["total"] > 0]
        max_tested_tier = tested_tiers[-1] if tested_tiers else "A1"
        min_tested_tier = tested_tiers[0] if tested_tiers else "A1"
        max_tier_idx = CEFR_LEVELS.index(max_tested_tier)
        min_tier_idx = CEFR_LEVELS.index(min_tested_tier)

        # 1. Calculate Estimated Vocabulary Size using Nation's Frequency Band Sampling Model
        # Baseline recognition floor
        est_vocab = 500.0

        for idx, tier in enumerate(CEFR_LEVELS):
            band_size = TIER_BAND_WORDS[tier]
            t_total = level_stats[tier]["total"]
            t_correct = level_stats[tier]["correct"]

            if t_total > 0:
                ratio = t_correct / t_total
                est_vocab += band_size * ratio
            else:
                if idx < min_tier_idx:
                    # Untested tiers lower than lowest tested:
                    # If user passed lowest tested tier with >= 50%, assume foundations known
                    lowest_ratio = level_stats[min_tested_tier]["correct"] / max(level_stats[min_tested_tier]["total"], 1)
                    if lowest_ratio >= 0.5:
                        est_vocab += band_size * 1.0
                    else:
                        est_vocab += band_size * lowest_ratio
                elif idx > max_tier_idx:
                    # Untested higher tiers contribute 0 words
                    est_vocab += 0.0
                else:
                    # Untested tier between tested tiers
                    est_vocab += band_size * 0.5

        # Speed bonus for fluent retrieval
        if 0.0 < avg_response_time <= 3.5 and raw_pct >= 60.0:
            est_vocab *= 1.03

        vocab_est = int(max(500, min(26000, round(est_vocab))))

        # 2. Derive Candidate CEFR Level from Estimated Vocab
        candidate_level = "A1"
        for lvl, min_words in [
            ("C2", 20000),
            ("C1", 13000),
            ("B2", 7500),
            ("B1", 4000),
            ("A2", 2000),
            ("A1", 0),
        ]:
            if vocab_est >= min_words:
                candidate_level = lvl
                break

        # 3. CEILING RULE: Never exceed the highest difficulty tested!
        if CEFR_LEVELS.index(candidate_level) > max_tier_idx:
            candidate_level = max_tested_tier

        # 4. FOUNDATIONS CHECK & GAP CONSTRAINT:
        # To achieve C1 or C2, user must not have completely failed B1 or B2
        if candidate_level in ("C1", "C2"):
            if level_stats["B2"]["total"] > 0 and level_stats["B2"]["correct"] == 0:
                candidate_level = "B2"
            if level_stats["B1"]["total"] > 0 and level_stats["B1"]["correct"] == 0:
                candidate_level = "A2"

        # To achieve A2, user must not have completely failed A2 if tested
        if candidate_level == "A2" and level_stats["A2"]["total"] > 0 and level_stats["A2"]["correct"] == 0:
            candidate_level = "A1"

        # 5. SAMPLE SIZE & RELIABILITY CHECK:
        is_reliable = (total >= 5)
        sample_warning = None
        if total < 5:
            is_reliable = False
            sample_warning = f"Preliminary estimate ({total} question{'s' if total > 1 else ''} answered — complete a full 10-12 question test for a certified rating)"
            if total <= 2 and candidate_level not in ("A1", "A2"):
                candidate_level = "A2" if candidate_level in ("B1", "B2") else "B1"

        labels = {
            "A1": "A1 - Beginner (Foundation)",
            "A2": "A2 - Elementary (Basic Working)",
            "B1": "B1 - Intermediate (Conversational)",
            "B2": "B2 - Upper Intermediate (Independent Fluency)",
            "C1": "C1 - Advanced (Academic & Professional)",
            "C2": "C2 - Mastery (Native / Erudite Fluency)",
        }

        if not is_reliable:
            cefr_label = f"{labels.get(candidate_level, candidate_level)} [Preliminary]"
        else:
            cefr_label = labels.get(candidate_level, candidate_level)

        # Response speed assessment
        if avg_response_time <= 0:
            speed_rating = "Untimed"
        elif avg_response_time <= 3.5:
            speed_rating = "Automatic / Fluent"
        elif avg_response_time <= 7.0:
            speed_rating = "Steady"
        else:
            speed_rating = "Deliberate"

        # Feedback message
        if not is_reliable:
            feedback = f"Preliminary estimate based on {total} question(s). Finish a complete 10-12 question benchmark for an official CEFR profile."
        elif candidate_level in ("C1", "C2"):
            feedback = "Exceptional lexical range! You demonstrate a commanding vocabulary capable of comprehending complex academic literature and subtle idioms."
        elif candidate_level == "B2":
            feedback = "Strong upper-intermediate proficiency! You demonstrate firm control of foundational and abstract vocabulary, ready to advance into specialized literature."
        elif candidate_level == "B1":
            feedback = "Good intermediate proficiency. You have established solid core everyday and conversational vocabulary, with great potential for B2 growth."
        else:
            feedback = "Foundational stage. Regular daily flashcard practice will quickly build your core active vocabulary."

        return {
            "score_pct": round(raw_pct, 1),
            "weighted_pct": round(raw_pct, 1),
            "correct_count": correct_count,
            "total_questions": total,
            "cefr_level": candidate_level,
            "cefr_label": cefr_label,
            "estimated_vocab_size": vocab_est,
            "speed_rating": speed_rating,
            "feedback": feedback,
            "level_breakdown": level_stats,
            "is_reliable": is_reliable,
            "sample_warning": sample_warning
        }

