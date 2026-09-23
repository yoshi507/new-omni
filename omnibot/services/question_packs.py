"""Preset icebreaker / dead-chat question packs."""
from __future__ import annotations

PACKS: dict[str, list[str]] = {
    "general": [
        "If you could have dinner with anyone (living or dead), who would it be?",
        "What's a small thing that always makes your day better?",
        "Would you rather explore space or the deep ocean?",
        "What's your go-to comfort food?",
        "What's a skill you'd love to learn this year?",
        "Morning person or night owl?",
        "What's the best advice you've ever received?",
        "If you could teleport anywhere right now, where?",
        "What's a hobby you've always wanted to try?",
        "Coffee, tea, or neither?",
        "What's your favourite season and why?",
        "Describe your perfect lazy day in three words.",
        "What's something you're proud of recently?",
        "If your life had a theme song, what would it be?",
        "What's the last show you binged?",
    ],
    "fun": [
        "Would you rather fight 100 duck-sized horses or one horse-sized duck?",
        "What's the weirdest food combination you actually like?",
        "If animals could talk, which would be the rudest?",
        "What's your most useless talent?",
        "Pineapple on pizza — yes or no?",
        "If you were a superhero, what would your power be?",
        "What's the dumbest thing you've done that somehow worked?",
        "Would you rather always be 10 minutes late or 20 minutes early?",
        "What's a conspiracy theory you half believe?",
        "If you had to rename yourself, what name would you pick?",
        "What's your chaotic alignment: lawfully chaotic or chaotically lawful?",
        "Hot take: share one unpopular opinion.",
        "If you could only eat one cuisine forever, which?",
        "What's the most overrated movie/show?",
        "Would you rather be able to fly or be invisible?",
    ],
    "gaming": [
        "What's the first game you ever played?",
        "Favourite genre right now — FPS, RPG, strategy, or indie?",
        "What's a game you keep coming back to?",
        "Best soundtrack in a game?",
        "Controller or keyboard and mouse?",
        "What's a game that made you emotional?",
        "Co-op or competitive — which do you prefer?",
        "Most underrated game you've played?",
        "If you could live in any game world, which one?",
        "What's your all-time favourite boss fight?",
        "Story-driven or pure gameplay?",
        "What's a game you wish had a sequel?",
        "Mobile, console, or PC for you?",
        "What's the longest you've played in one session?",
        "Favourite gaming snack?",
    ],
    "anime": [
        "What was your gateway anime?",
        "Favourite anime genre — shonen, slice of life, mecha, romance?",
        "Best anime opening of all time?",
        "Character you'd want as a best friend?",
        "Overrated anime hot take?",
        "Manga or anime first?",
        "Favourite studio (MAPPA, Ufotable, Kyoto Animation)?",
        "Which anime world would you least want to live in?",
        "Best villain in anime?",
        "Slice of life comfort watch?",
        "Favourite filler episode that actually slapped?",
        "Who's your favourite protagonist?",
        "Anime that deserves more recognition?",
        "Dub or sub?",
        "If you could have one anime power, which?",
    ],
    "science": [
        "What's a science fact that still blows your mind?",
        "Space or deep sea — which is scarier?",
        "If you could clone any animal, which?",
        "Favourite planet (besides Earth)?",
        "Would you board a one-way trip to Mars?",
        "What's a technology you're most excited about?",
        "Physics, biology, chemistry, or astronomy?",
        "If time travel existed, past or future?",
        "What's the coolest animal adaptation you know?",
        "AI: helpful tool or sci-fi warning?",
        "Would you rather explore a black hole or an alien ocean?",
        "Favourite science documentary or channel?",
        "What scientific mystery do you wish was solved?",
        "Climate tech or space tech — where should funding go?",
        "If you could invent one thing, what would it be?",
    ],
    "facts": [
        "Share a fun fact you know (any topic)!",
        "What's a random skill fact about yourself?",
        "True or false: octopuses have three hearts. (True!)",
        "What's the most surprising thing you learned this week?",
        "Name a country you'd love to visit and one fact about it.",
        "What's a myth people still believe?",
        "Share a weird history fact.",
        "What's something most people get wrong about your hobby?",
        "Favourite did-you-know fact?",
        "What's a food origin fact you find interesting?",
        "Language fact: share a word you love from another language.",
        "Animal fact time — drop one!",
        "What's a common saying that isn't actually true?",
        "Share a fact about your hometown.",
        "What's the most useless fact you remember?",
    ],
    "music": [
        "What song is stuck in your head right now?",
        "Favourite genre to work/study to?",
        "Best concert you've been to (or dream concert)?",
        "Album you could listen to on loop?",
        "Guilty pleasure song?",
        "Vinyl, streaming, or both?",
        "Artist that changed how you listen to music?",
        "Favourite decade for music?",
        "Song that always hypes you up?",
        "Acoustic or electronic vibes today?",
    ],
    "movies": [
        "Favourite movie of all time?",
        "Best plot twist you've seen?",
        "Comfort movie when you're sick?",
        "Overrated blockbuster?",
        "Animated or live-action preference?",
        "Movie you can quote by heart?",
        "Horror: love it or nope?",
        "Best film soundtrack?",
        "If you directed a sequel, which franchise?",
        "Underrated gem everyone should watch?",
    ],
}

PACK_LABELS = {
    "general": "General icebreakers",
    "fun": "Fun and chaotic",
    "gaming": "Gaming",
    "anime": "Anime",
    "science": "Science",
    "facts": "Fun facts",
    "music": "Music",
    "movies": "Movies and TV",
}


def list_packs() -> list[str]:
    return sorted(PACKS.keys())


def questions_for_packs(pack_ids: list[str] | None) -> list[str]:
    if not pack_ids:
        pack_ids = ["general"]
    out: list[str] = []
    seen: set[str] = set()
    for pid in pack_ids:
        key = str(pid).strip().lower()
        for q in PACKS.get(key) or []:
            if q not in seen:
                seen.add(q)
                out.append(q)
    return out


def pick_question(
    pack_ids: list[str] | None,
    custom: list[str] | None,
) -> str:
    import random

    pool = list(questions_for_packs(pack_ids))
    for q in custom or []:
        q = str(q).strip()
        if q and q not in pool:
            pool.append(q)
    if not pool:
        pool = PACKS["general"][:]
    return random.choice(pool)
