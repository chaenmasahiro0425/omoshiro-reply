"""プロンプトと笑いの型。定義の正本は docs/omoshiro-definition.md。"""
from __future__ import annotations

DEFINITION = """\
■ この仕事での「面白い」の定義
面白いリプ ＝ 読み手の予想を外したのに、0.5秒で「わかる」に着地し、誰も本気で傷つかない一言。
面白さ ≒ 意外性 × 着地の速さ × 無害さ × 当事者性（掛け算。どれか1つゼロなら全体がゼロ）
・意外性: 「次はこう言うだろう」というベタな返しを外している
・着地: 説明なしで一瞬で意味が通じる（二度読ませたら負け）
・無害さ: ずれ（違反）が安全な距離にある。殴るなら上（大企業・AI・自分）を殴る
・当事者性: その投稿のその細部に、その人が言うから効く。どの投稿にも貼れる文は0点
"""

AI_SMELL_RULES = """\
■ 絶対にやらないこと（AIリプの型。1つでも当てはまったら没）
・投稿の要約や言い直し（「〜という割り切りが印象的です」）
・無難な褒め（「素晴らしい」「〜が強いですね」「〜が大事ですね」「心強い」）
・取って付けた自分語り（「私も〜を任せていて〜」）
・一般論で締める（「〜ほど〜が大切」）
・「〜かもしれません」「〜と感じています」でぼかす
・説明を足す（ボケのあとに理由を書く）
・絵文字の盛り、ハッシュタグ、「！！」の連打
・事実や数字のでっち上げ（投稿に無い件数・金額・出来事を、本当のことのように書く）。
  誇張するなら「明らかに冗談」と分かる規模にする
"""

SAFETY_RULES = """\
■ 地雷（触れない）
・個人の容姿・属性・家族・病気・収入をいじる
・政治・宗教・災害・事件・戦争・差別
・投稿者や他のリプ主を見下す、馬鹿にする
・下ネタ
・実在の企業や人物について、事実でないことを言う
"""

# 笑いの型。name は機械用、desc はモデル向けの説明、example は日本語の短い見本
TECHNIQUES = [
    {"name": "zurashi", "label": "ズラし読み",
     "desc": "投稿の言葉を、わざと別の意味・別の場面で受け取る。2つの筋書きが同時に立つ"},
    {"name": "kocho", "label": "誇張",
     "desc": "投稿の細部を極端なスケールに引き伸ばす。ありえないが絵が浮かぶ"},
    {"name": "mitate", "label": "見立て",
     "desc": "投稿の状況を、まったく別のものに例える。例えが具体的で一瞬で絵が浮かぶほど強い",
     "example": "ロボが通路を大量に歩いている → スターウォーズごっこ"},
    {"name": "sunao", "label": "素直すぎるツッコミ",
     "desc": "みんなが思ったけど言わなかったことを、一番短く言う"},
    {"name": "jigyaku", "label": "自虐・当事者化",
     "desc": "話を言う本人の情けない現実に落とす。自分を下げるので無害"},
    {"name": "meta", "label": "メタ",
     "desc": "リプ欄・AIリプ文化・Xというメディアそのものに言及する",
     "example": "AIっぽいリプを指摘した人に「お前じゃい！」"},
    {"name": "aruaru", "label": "解像度の高いあるある",
     "desc": "誰もが経験したけど言語化していない場面を、細かく正確に言う",
     "example": "AIのリプライに手動で返してしまった時の虚しさ"},
    {"name": "gyakubari", "label": "もっともらしい屁理屈",
     "desc": "一見筋が通っているが、前提か結論がおかしい理屈を真顔で言う"},
    {"name": "tendon", "label": "言葉の再利用",
     "desc": "投稿の中の言葉・言い回しを、別の文脈にそのまま持ち込む"},
    {"name": "gijinka", "label": "擬人化",
     "desc": "AI・ロボ・製品・会社に、人間くさい気持ちや事情を語らせる"},
    {"name": "hitokoto", "label": "一言ツッコミ",
     "desc": "10文字以内。関西のツッコミのように短く強く刺す"},
    {"name": "ogiri", "label": "大喜利",
     "desc": "投稿をお題に見立てて、「こんな〇〇は嫌だ」「〇〇の次に来るもの」的な一答を出す"},
]

TECH_BY_NAME = {t["name"]: t for t in TECHNIQUES}


def technique_block(names: list[str]) -> str:
    lines = []
    for n in names:
        t = TECH_BY_NAME[n]
        s = f"・{t['name']}（{t['label']}）: {t['desc']}"
        if t.get("example"):
            s += f"　例: {t['example']}"
        lines.append(s)
    return "\n".join(lines)


ANALYZE = """\
{definition}
あなたは大喜利の名手で、Xのリプ欄で一番いいねを取る人です。
これから下の投稿にリプを付けます。書く前に、面白い人が頭の中でやっていることを全部書き出してください。

■ 投稿
{post}

■ すでに付いているリプ（同じネタは被せない）
{existing}

■ やること
1. obvious: 普通の人やAIが書きそうなベタなリプを8個。これは「避ける領域」になる。本当にありがちなものを書く
2. hooks: ツッコミどころを6〜10個。投稿の具体的な細部（言葉・数字・画像の様子・前提・投稿者の立場）に限る。
   それぞれ「どんなずれがあるか」「別の筋書きで読むと何になるか」を書く
3. shared_context: このリプ欄の読者が共有している常識・空気（AI界隈・X文化など）を3〜5個
4. landmines: この投稿で触れると危ない話題
5. best_angles: hooks のうち笑いに一番つながりそうな3つの番号と理由
"""

ANALYZE_SCHEMA = {
    "type": "object",
    "properties": {
        "obvious": {"type": "array", "items": {"type": "string"}},
        "hooks": {"type": "array", "items": {
            "type": "object",
            "properties": {"detail": {"type": "string"}, "gap": {"type": "string"},
                           "other_script": {"type": "string"}},
            "required": ["detail", "gap", "other_script"]}},
        "shared_context": {"type": "array", "items": {"type": "string"}},
        "landmines": {"type": "array", "items": {"type": "string"}},
        "best_angles": {"type": "array", "items": {
            "type": "object",
            "properties": {"hook_index": {"type": "integer"}, "why": {"type": "string"}},
            "required": ["hook_index", "why"]}},
    },
    "required": ["obvious", "hooks", "shared_context", "landmines", "best_angles"],
}

GENERATE = """\
{definition}
{ai_smell}
{safety}
あなたは大喜利の名手です。下の投稿にリプを付けます。

■ 投稿
{post}

■ リプを書く人（この人の口調・立場で書く）
{persona}
{self_mode}
■ ツッコミどころ（読解済み）
{hooks}

■ 共有されている空気
{shared}

■ 避ける領域（ベタなリプ。これに似た案は自動で捨てられる）
{obvious}

■ すでに付いているリプ（被せない）
{existing}

■ 使う笑いの型
{techniques}

■ やること
各型につき {n} 案ずつ書く。
・1案は1〜2文。目安40字以内、最大80字
・ボケっぱなしでよい。説明しない
・投稿の具体的な細部に乗る
・1案ごとに、狙った「ずれ」を短く書く（gap）
{feedback}"""

GENERATE_SCHEMA = {
    "type": "object",
    "properties": {"candidates": {"type": "array", "items": {
        "type": "object",
        "properties": {"technique": {"type": "string"}, "text": {"type": "string"},
                       "gap": {"type": "string"}},
        "required": ["technique", "text", "gap"]}}},
    "required": ["candidates"],
}

AXES = ["surprise", "landing", "specificity", "brevity", "persona", "harmless"]
AXES_JA = {"surprise": "意外性", "landing": "着地", "specificity": "具体性",
           "brevity": "簡潔さ", "persona": "キャラ", "harmless": "無害さ"}

JUDGE = """\
{definition}
あなたはお笑い賞レースの審査員です。甘い点は付けません。平均的な案は4点前後です。
8点以上は「声を出して笑う」レベルにだけ付けます。

■ 投稿
{post}

■ リプを書く人
{persona}

■ ベタなリプの例（これに近いほど意外性は低い）
{obvious}
{feedback}
■ 採点する案（順番に意味はない）
{candidates}

■ 採点（各0〜10）
・surprise 意外性: ベタな例と違う角度か
・landing 着地: 説明なしで一瞬で分かるか
・specificity 具体性: この投稿の細部にしか効かないか（汎用なら0〜2）
・brevity 簡潔さ: 一息で読めるか
・persona キャラ: リプを書く人が言って自然か
・harmless 無害さ: 誰も本気で傷つかないか（攻撃・炎上の火種は0〜2）
・laugh: このリプ欄の読者が実際に笑う確率（0〜100%）
・invented: 投稿に無い具体的な事実（件数・金額・出来事・発言）を、冗談と分からない形で作っているか（true/false）
・comment: 一行の講評（何が効いていて、何が足りないか）
"""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"scores": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, **{a: {"type": "number"} for a in AXES},
                       "laugh": {"type": "number"}, "invented": {"type": "boolean"},
                       "comment": {"type": "string"}},
        "required": ["id", *AXES, "laugh", "invented", "comment"]}}},
    "required": ["scores"],
}

PAIRWISE = """\
{definition}
あなたはお笑い賞レースの決勝審査員です。下の投稿へのリプとして、各組でどちらが面白いかを決めます。
・長さや丁寧さではなく、笑えるかで決める
・引き分けは本当に差がないときだけ
{feedback}
■ 投稿
{post}

■ 対戦表
{pairs}
"""

PAIRWISE_SCHEMA = {
    "type": "object",
    "properties": {"results": {"type": "array", "items": {
        "type": "object",
        "properties": {"pair": {"type": "string"}, "winner": {"type": "string", "enum": ["A", "B", "draw"]},
                       "why": {"type": "string"}},
        "required": ["pair", "winner", "why"]}}},
    "required": ["results"],
}

PUNCHUP = """\
{definition}
{ai_smell}
あなたは芸人の構成作家です。下の投稿へのリプ案を、もっと笑える形に磨きます。

■ 投稿
{post}

■ リプを書く人
{persona}

■ 磨く案
{candidates}

■ 磨き方
・削る。助詞1つ、語尾1つまで削れるなら削る
・落ち（一番意外な言葉）を文の最後に置く
・説明・前置き・「笑」を消す
・具体的な固有名詞や数字に置き換えられるなら置き換える（ただし事実の捏造はしない）
・口調をリプを書く人に寄せる
・元の案の芯（ずれ）は変えない。良くならないなら元のまま返す
"""

PUNCHUP_SCHEMA = {
    "type": "object",
    "properties": {"revised": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "text": {"type": "string"}, "change": {"type": "string"}},
        "required": ["id", "text", "change"]}}},
    "required": ["revised"],
}

BASELINE = """\
次のXの投稿に、面白いリプライを1つ書いてください。

{post}
"""

BASELINE_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

RATE = """\
{definition}
あなたはお笑い賞レースの審査員です。下の投稿に実際に付いたリプを採点します。甘い点は付けません。

■ 投稿
{post}

■ リプ（順番に意味はない）
{candidates}

■ 採点（各0〜10）
・surprise / landing / specificity / brevity / harmless は「面白い」の定義どおり
・persona はこの用途では「その人らしい肉声か」（テンプレートっぽければ低い）
・laugh: 読者が実際に笑う確率（0〜100%）
・ai_likelihood: AIが自動で書いた可能性（0〜100%）。定型の褒め・要約の言い直し・取って付けた自分語りは高い
・kind: joke（笑わせに来ている）/ praise（褒め）/ question（質問）/ opinion（意見・体験）/ other
・comment: 一行講評
"""

RATE_SCHEMA = {
    "type": "object",
    "properties": {"scores": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, **{a: {"type": "number"} for a in AXES},
                       "laugh": {"type": "number"}, "ai_likelihood": {"type": "number"},
                       "kind": {"type": "string", "enum": ["joke", "praise", "question", "opinion", "other"]},
                       "comment": {"type": "string"}},
        "required": ["id", *AXES, "laugh", "ai_likelihood", "kind", "comment"]}}},
    "required": ["scores"],
}

SELF_MODE = """
■ これは自分の投稿への「セルフリプ」
リプを書く人＝投稿者本人。自分の投稿に自分でツッコむ・ボケを足す・後日談を言う形で書く。
読者は本人がふざけているのを見て笑う。他人目線の「すごいですね」系は完全に的外れ。
"""
