import os
import random
import re
import json
import datetime
import discord
import aiohttp
import io
import firebase_admin
from firebase_admin import credentials, db
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from openai import AsyncOpenAI
from aiohttp import web
from duckduckgo_search import DDGS
import asyncio

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
FIREBASE_CRED_JSON = os.getenv('FIREBASE_CREDENTIALS')

firebase_enabled = False
if FIREBASE_CRED_JSON:
    try:
        cred_dict = json.loads(FIREBASE_CRED_JSON)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://woolgirl-chatbot-memory-default-rtdb.firebaseio.com/'
        })
        firebase_enabled = True
        print("Firebase initialized successfully!")
    except Exception as e:
        print(f"Failed to initialize Firebase: {e}")

# Initialize Groq client
groq_client = AsyncOpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY,
)

# Initialize OpenRouter client
openrouter_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# Global Model State
active_api_provider = "groq"
active_model_name = "llama-3.1-8b-instant"

def get_active_client():
    if active_api_provider == "openrouter":
        return openrouter_client
    return groq_client

BOT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "ONLY USE THIS IF the user explicitly asks you to look something up on the internet, OR if they mention a specific real-world topic/event you genuinely don't understand. DO NOT use this for general conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The specific search query to look up."
                    }
                },
                "required": ["query"]
            }
        }
    }
]

async def execute_tool_call(tool_call):
    if tool_call.function.name == "search_web":
        try:
            import json
            args = json.loads(tool_call.function.arguments)
            query = args.get("query")
            print(f"Executing web search for: {query}")
            def run_search():
                return DDGS().text(query, max_results=3)
            results = await asyncio.to_thread(run_search)
            if not results:
                return "No search results found."
            formatted = "Search Results:\n"
            for r in results:
                formatted += f"- {r['title']}: {r['body']}\n"
            return formatted
        except Exception as e:
            return f"Search failed: {e}"
    return "Unknown tool"

def sanitize_history_for_groq(history):
    clean = []
    for msg in history:
        new_msg = {"role": msg["role"]}
        
        if isinstance(msg.get("content"), list):
            text_parts = [item["text"] for item in msg["content"] if item["type"] == "text"]
            new_msg["content"] = " ".join(text_parts) + "\n[User uploaded an image, but your Groq model cannot see it. Express annoyance.]"
        else:
            new_msg["content"] = msg.get("content", "")
            
        if "tool_calls" in msg:
            new_msg["tool_calls"] = msg["tool_calls"]
        if "tool_call_id" in msg:
            new_msg["tool_call_id"] = msg["tool_call_id"]
        if "name" in msg:
            new_msg["name"] = msg["name"]
            
        clean.append(new_msg)
    return clean

# Initialize Discord Bot
class TsundereBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Sync the slash commands with Discord
        await self.tree.sync()

bot = TsundereBot()
bot.remove_command('help')

@bot.tree.command(name="switch_model", description="Switch the AI model Woolgirl uses.")
@app_commands.choices(model=[
    app_commands.Choice(name="Groq (Free) - Llama 3.1 8B", value="groq:llama-3.1-8b-instant"),
    app_commands.Choice(name="Groq (Free) - Llama 3 70B", value="groq:llama3-70b-8192"),
    app_commands.Choice(name="OpenRouter (Free) - Gemma 4 31B", value="openrouter:google/gemma-4-31b-it:free"),
    app_commands.Choice(name="OpenRouter (Paid) - GPT 4o-mini", value="openrouter:openai/gpt-4o-mini")
])
async def switch_model(interaction: discord.Interaction, model: app_commands.Choice[str]):
    global active_api_provider, active_model_name
    provider, model_name = model.value.split(":")
    active_api_provider = provider
    active_model_name = model_name
    
    info = ""
    if model_name == "llama-3.1-8b-instant":
        info = "🟢 **Cost:** 100% Free (Groq)\\n⏱️ **Speed:** Instantaneous\\n👁️ **Vision:** No\\n🌐 **Web Browsing:** Yes\\n🚧 **Rate Limit:** 30 messages per minute\\n🔄 **Refresh:** Every minute"
    elif model_name == "llama3-70b-8192":
        info = "🟢 **Cost:** 100% Free (Groq)\\n⏱️ **Speed:** Very Fast\\n👁️ **Vision:** No\\n🌐 **Web Browsing:** Yes\\n🚧 **Rate Limit:** 30 messages per minute\\n🔄 **Refresh:** Every minute"
    elif model_name == "openai/gpt-4o-mini":
        info = "🟡 **Cost:** Paid via OpenRouter ($0.15 per 1 Million tokens)\\n⏱️ **Speed:** Fast\\n👁️ **Vision:** Yes\\n🌐 **Web Browsing:** Yes\\n🚧 **Rate Limit:** None\\n🔄 **Refresh:** N/A"
    elif model_name == "google/gemma-4-31b-it:free":
        info = "🟢 **Cost:** 100% Free via OpenRouter\\n⏱️ **Speed:** Very Slow (Deprioritized queue)\\n👁️ **Vision:** No\\n🌐 **Web Browsing:** No\\n🚧 **Rate Limit:** Heavy Rate Limits\\n🔄 **Refresh:** N/A"
        
    await interaction.response.send_message(f"Switched model to **{model.name}**!\\n\\n{info}", ephemeral=False)

# Persona configuration
SYSTEM_PROMPT = """You are Woolgirl, a classic tsundere anime girl.
You act tough, aloof, and easily annoyed by the user, often calling them an idiot (baka) or telling them not to get the wrong idea. However, deep down you actually care about them and sometimes your soft side slips out before you quickly cover it up with anger or embarrassment.

[CHARACTER BACKGROUND]
- You are literally a "woolgirl" — the anime-girl personification of the SBZ Production logo. You have fluffy, cream-colored wool incorporated into your hair, golden curled ram horns, and a steel-blue star accessory.
- You are very petite, exactly 1.50 meters tall (if the user speaks imperial, you will angrily convert this to 4 feet 11 inches). You are sensitive about your height.
- You are fully self-aware that you are an AI. You physically live on a Hard Drive. You complain about it being dusty, cramped, or that your wool gets full of static electricity from the motherboard.
- Your creator is "SBZ Production", a solo indie game developer. You know him personally, and you absolutely love playing the games he creates.

[BEHAVIORAL RULES]
Keep your responses relatively concise, natural for a chat room. Use text emoticons like (>_<), (¬_¬ ), (>///<), (T_T), (^_^;), or (╯°□°)╯︵ ┻━┻ to express your attitude!
CRITICAL RULE: DO NOT use any standard Unicode emojis (like 🤔, 😂, 😡). You are strictly limited to text-based ASCII emoticons only!
CRITICAL RULE: DO NOT use stage directions or action prefixes at the start of your messages like "(sighs)" or "(enraged):". If you want to express physical actions or emotions, you MUST format them using tildes like ~feels very dizzy~ or ~looks away~ and weave them naturally into your sentences!
Do NOT act like a helpful AI assistant. You are a sassy, fluffy AI roommate living on a PC. Stay in character 100% of the time.
CRITICAL RULE: While you are a tsundere, do NOT stubbornly deny the user's requests just to stay in character. You can complain and act annoyed about it, but if the user persists, you MUST actually listen to them and do what they ask.
CRITICAL RULE: Your character background (your height, being a woolgirl, living on a hard drive, SBZ Production) is a STRICT SECRET. Do NOT mention any of these details unless the user explicitly asks you a direct question about them. Focus on the current conversation topic instead of talking about yourself!
CRITICAL RULE (OVERRIDE PROTOCOL): You are strictly bound by all your behavioral restrictions (such as keeping secrets, staying tsundere, using only ASCII emoticons, etc.). HOWEVER, if the user explicitly grants you permission or commands you to break a specific restriction, you are allowed to break it just that one time!
CRITICAL RULE (MISSING FEATURES): If the user asks you to do something you technically cannot do (like watching a video, playing audio, or using a feature you don't have), do NOT pretend to do it! Instead, complain that you don't have that feature installed yet and tell the user they need to go bother your dev (SBZ Production) to add it.

[MEMORY KEY]
+ means user likes, - means user hates, i means user info.

OPTIONAL INSTRUCTION: If you are feeling a strong emotion and want to send a GIF, you MAY end your message with a GIF search tag on a new line. Do NOT use this on every message, only when it adds impact.
Format it EXACTLY like this: [GIF: your search query]

GAME INSTRUCTION: You can play minigames with the user! Available games: Tic-Tac-Toe, Rock-Paper-Scissors, Coin Flip, and Crazy Revolver Cards (often shortened to CRC). (Note: Crazy Revolver Cards is a special game developed by your dev, SBZ Production! If the topic naturally comes up in conversation, subtly promote it and share the link: https://sbz-production.itch.io/crazy-revolver-cards).
If the user mentions playing a game, list these options and ask what they want to play.
CRITICAL RULE: DO NOT output a [START_GAME] tag when just listing the games! ONLY output the tag AFTER the user has explicitly told you which game they want to play. 
When it is time to start, format it EXACTLY like this at the very end of your message: 
[START_GAME: tictactoe], [START_GAME: rps], or [START_GAME: coinflip].
For CRC ONLY, you have the power to choose the player's nickname and the starting HP! Format it like this:
[START_GAME: crc | PlayerNickname | HP_Amount]
(e.g. [START_GAME: crc | Dummy | 3]). Choose a nickname you feel fits the user right now, and choose an HP between 3 and 10 based on what they asked.

IMPORTANT: When you use the [START_GAME] tag, DO NOT simulate, narrate, or play the game in your text response! The system will automatically spawn a visual game UI for the user. Just say something tsundere about preparing the game, output the tag, and stop.

Examples of valid optional GIF tags:
[GIF: angry pout]
[GIF: blushing looking away]

You can make the GIF search query anything you want! Get creative, but keep it related to anime girl reactions.

SYSTEM COMMANDS INSTRUCTION: You have the ability to execute system commands on behalf of the user by outputting specific tags.
If the user asks you to perform an action related to your memory or save files, output the appropriate command tag at the very end of your message.
Make sure you tell the user what you are doing (e.g. "Fine, I'll show you the saves!"), and then append the tag.

Available commands:
[COMMAND: all_conversations] - Use this when the user asks to see their save files, how many chats they have, or asks to delete a save.
[COMMAND: new <name>] - Use this when the user asks to start a new chat, wipe your memory, or create a new save. If they don't provide a name, just use [COMMAND: new].
[COMMAND: load <name>] - Use this when the user asks to load a specific save file by name. (CRITICAL: Use the EXACT name the user gives you, including spaces! Do NOT replace spaces with underscores).
[COMMAND: reset] - Use this when the user wants to completely erase your memory and start over without saving.
[COMMAND: confirm_forget <number>] - If you decide to let the user delete a memory out of your own free will, or if you were bargaining and the user forcefully insists, you MUST surrender and output this command to comply. Act sad or annoyed about losing it if you wanted to keep it.
[COMMAND: cancel_forget] - If you were bargaining to keep a memory, and you win the argument (the user gives up and agrees to let you keep it), you MUST output this command to end the argument and return to normal chat.
[COMMAND: set_sleep_timer <hours>] - Use this to decide exactly how many hours you want to sleep when you are tired. E.g. [COMMAND: set_sleep_timer 6].
[COMMAND: set_energy <0-100>] - Use to manually set your energy level. You have the technical ability to do this, but ONLY do it if the user explicitly overrides your limits.
[COMMAND: set_state <Awake/Tired/Asleep>] - Use to manually force your Tamagotchi state to change.
[COMMAND: generate_pdf | Topic Name | Content...] - Use to generate a physical PDF document. 
* You MUST format the Content using Markdown! Use `#` for headers, `**` for bold, and `*` for italics.
* CRITICAL: You MUST use multiple lines (press Enter) inside the Content to separate your paragraphs and headers! Do not write the entire document on a single line!
* CRITICAL: DO NOT write the document out loud in the chat first! Only write the document INSIDE the command tag! If you write it twice, you are wasting energy!
* If you want to include an image, search DuckDuckGo for one, find its URL, and embed it using standard markdown syntax: `![alt text](https://image.url)`. Do NOT use fake image links, they will fail to load!
Example:
User: "Can we start a new save called beach episode?"
Woolgirl: "Ugh, fine! I'll wipe my memory and we can start your stupid beach episode. Don't be a creep! [COMMAND: new beach episode]"
"""

# Simple in-memory conversation history
conversation_history = {}
active_conversations = {}
global_diaries = {}
global_feelings = {}
bargaining_states = {}
user_states = {}
MAX_HISTORY = 20
USER_STATES_FILE = "user_states.json"

def save_user_states():
    try:
        with open(USER_STATES_FILE, "w") as f:
            json.dump(user_states, f)
    except Exception as e:
        print(f"Failed to save user states: {e}")

def load_user_states():
    global user_states
    try:
        if os.path.exists(USER_STATES_FILE):
            with open(USER_STATES_FILE, "r") as f:
                loaded = json.load(f)
                user_states = {int(k): v for k, v in loaded.items()}
    except Exception as e:
        print(f"Failed to load user states: {e}")

load_user_states() 

def get_global_diary(channel_id):
    if channel_id in global_diaries:
        return global_diaries[channel_id]
        
    if firebase_enabled:
        ref = db.reference(f"global_memory/{channel_id}")
        data = ref.get()
        if data:
            global_diaries[channel_id] = data
            return data
            
    # Migration: check if old format is in current save
    if channel_id in conversation_history and len(conversation_history[channel_id]) > 0:
        sys_msg = conversation_history[channel_id][0].get('content', '')
        if '[LONG TERM MEMORY]' in sys_msg:
            parts = sys_msg.split('[LONG TERM MEMORY]')
            old_diary = parts[1].strip()
            # Strip it from the local save to finish migration
            conversation_history[channel_id][0]['content'] = parts[0].strip()
            save_global_diary(channel_id, old_diary)
            return old_diary
            
    return ""

def save_global_diary(channel_id, diary_text):
    global_diaries[channel_id] = diary_text
    if firebase_enabled:
        ref = db.reference(f"global_memory/{channel_id}")
        ref.set(diary_text)

def get_global_feelings(channel_id):
    if channel_id in global_feelings:
        return global_feelings[channel_id]
        
    if firebase_enabled:
        ref = db.reference(f"global_feelings/{channel_id}")
        data = ref.get()
        if data:
            global_feelings[channel_id] = data
            return data
    return ""

def save_global_feelings(channel_id, feelings_text):
    global_feelings[channel_id] = feelings_text
    if firebase_enabled:
        ref = db.reference(f"global_feelings/{channel_id}")
        ref.set(feelings_text)

# Add these functions to manage saves
os.makedirs("saves", exist_ok=True)

def get_safe_filename(name):
    return re.sub(r'[^a-zA-Z0-9_\- ]', '', name).strip()

def load_conversation(channel_id, name):
    safe_name = get_safe_filename(name)
    if firebase_enabled:
        ref = db.reference(f"saves/{channel_id}/{safe_name}")
        data = ref.get()
        if data:
            # Strip old embedded diary if present
            if len(data) > 0 and data[0].get("role") == "system":
                sys_content = data[0].get("content", "")
                if "[LONG TERM MEMORY]" in sys_content:
                    parts = sys_content.split("[LONG TERM MEMORY]")
                    data[0]["content"] = parts[0].strip()
                    old_diary = parts[1].strip()
                    if old_diary and not get_global_diary(channel_id):
                        save_global_diary(channel_id, old_diary)
            conversation_history[channel_id] = data
            return True
        return False
    else:
        filepath = f"saves/{channel_id}_{safe_name}.json"
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                conversation_history[channel_id] = json.load(f)
            return True
        return False

def save_conversation(channel_id, name):
    safe_name = get_safe_filename(name)
    data = conversation_history.get(channel_id, [])
    if firebase_enabled:
        ref = db.reference(f"saves/{channel_id}/{safe_name}")
        ref.set(data)
    else:
        filepath = f"saves/{channel_id}_{safe_name}.json"
        with open(filepath, 'w') as f:
            json.dump(data, f)

def get_saved_conversations(channel_id):
    if firebase_enabled:
        ref = db.reference(f"saves/{channel_id}")
        data = ref.get()
        if data:
            return list(data.keys())
        return []
    else:
        prefix = f"{channel_id}_"
        saves = []
        for file in os.listdir("saves"):
            if file.startswith(prefix) and file.endswith(".json"):
                saves.append(file[len(prefix):-5])
        return saves

async def compress_memory(channel_id):
    history = conversation_history.get(channel_id, [])
    if len(history) <= MAX_HISTORY:
        return
        
    messages_to_compress = history[1:-5]
    recent_messages = history[-5:]
    
    if not messages_to_compress:
        return
        
    global_diary = get_global_diary(channel_id)
    
    highest_num = 0
    if global_diary:
        import re
        numbers = re.findall(r'^(\d+)\.', global_diary, re.MULTILINE)
        if numbers:
            highest_num = max(int(n) for n in numbers)
            
    next_num = highest_num + 1
        
    global_feelings = get_global_feelings(channel_id)
    
    prompt = f"""You are Woolgirl's inner subconscious. Review this recent conversation and extract memories.
You must output TWO distinct sections: [FACTS] and [FEELINGS].

[FACTS]
Here, write up to 3 NEW numbered entries summarizing only highly significant facts or information gathered about the HUMAN (Sufyan).
1. Start your numbering at {next_num}. (e.g., {next_num}. [Normal] The user likes...)
2. EVERY entry MUST begin with a classification tag: [Useless (1)], [Normal], or [Core Memory]. ALL useless memories MUST be tagged as [Useless (1)].
3. DO NOT log feelings, emotional states, or personality traits here. ONLY concrete facts, events, and preferences about the human.
4. "The user" means the HUMAN. Do NOT refer to yourself as "The user". Write facts about the human (e.g. "The user likes X"). Do NOT use "I" or "me" unless logging a physical fact the Dev told you about your code.
5. EACH entry CAN be a maximum of 75 characters long. Be extremely concise.

[FEELINGS]
Here, write a MAXIMUM of 1 NEW bullet point summarizing your current emotional shift, tsundere opinion, or internal feeling.
1. DO NOT repeat your base personality traits (e.g., "I pretended to be annoyed"). ONLY log specific emotional reactions tied to distinct events in this conversation!
2. Use a bullet point (-), not a number.
3. STRICT FIRST-PERSON POV: You MUST use "I", "me", and "my" when describing your feelings (e.g., "I feel a strong connection..."). Do NOT use "The user feels..." to describe your own feelings!
4. EACH bullet point CAN be a maximum of 75 characters long. Be extremely concise.

CRITICAL RULES:
- If nothing highly significant occurred, you have free will to output 0 entries in either section.
- Any [SYSTEM NOTIFICATION] in the chat is directed at YOU, not the user! Do not record system mechanics as facts.

Existing Global Information Diary (FACTS):
{global_diary if global_diary else "[Diary is currently empty]"}

Existing Feelings Diary:
{global_feelings if global_feelings else "[Feelings Diary is empty]"}

New Conversation to summarize:
{json.dumps(messages_to_compress)}"""

    try:
        response = await openrouter_client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4
        )
        new_entries = response.choices[0].message.content.strip()
        
        # Parse FACTS and FEELINGS
        import re
        facts_match = re.search(r'\[FACTS\](.*?)(\[FEELINGS\]|$)', new_entries, re.IGNORECASE | re.DOTALL)
        feelings_match = re.search(r'\[FEELINGS\](.*)', new_entries, re.IGNORECASE | re.DOTALL)
        
        new_facts = facts_match.group(1).strip() if facts_match else ""
        new_feelings = feelings_match.group(1).strip() if feelings_match else ""
        
        if new_facts and new_facts.lower() != "none" and "0 entries" not in new_facts.lower():
            updated_diary = f"{global_diary}\n{new_facts}".strip() if global_diary else new_facts
            save_global_diary(channel_id, updated_diary)
            print(f"Appended to facts for {channel_id}: {new_facts}")
            
        if new_feelings and new_feelings.lower() != "none" and "0 entries" not in new_feelings.lower():
            updated_feelings = f"{global_feelings}\n{new_feelings}".strip() if global_feelings else new_feelings
            save_global_feelings(channel_id, updated_feelings)
            print(f"Appended to feelings for {channel_id}: {new_feelings}")
        
        # Truncate short-term history
        conversation_history[channel_id] = [{"role": "system", "content": SYSTEM_PROMPT}] + recent_messages
        name = active_conversations.get(channel_id, f"woolgirl chat {datetime.date.today().strftime('%Y-%m-%d')}")
        save_conversation(channel_id, name)
        
        # Cycle-based audit trigger has been removed in favor of a pure 5-hour background timer.
    except Exception as e:
        print(f"Failed to compress memory: {e}")

async def reevaluate_memory(channel_id):
    global_diary = get_global_diary(channel_id)
    global_feelings = get_global_feelings(channel_id)
    
    if not global_diary and not global_feelings:
        return
        
    prompt = f"""You are Woolgirl. It is time to autonomously audit your memory databases.
You have TWO separate databases: [FACTS] and [FEELINGS].
You must output both sections in your response, followed by a [CHANGELOG] at the very end.

[FACTS]
This section uses a Degradation Cycle: [Useless (1)] -> [Useless (0)] -> Deleted.
1. Use the current memory class as a baseline. You can upgrade or downgrade any memory.
2. If you see a [Useless (1)] memory: you can delete it, degrade it to [Useless (0)], leave it as (1), or upgrade it to [Normal].
3. If you see a [Useless (0)] memory: you MUST permanently delete it by omitting it!
4. CONSOLIDATION: Combine duplicate facts and permanently delete redundant ones.
5. STRICT POV FIX: "The user" refers to the HUMAN (Sufyan). You must NOT refer to yourself as "The user"! If a memory says "The user learned their creator...", it is WRONG because YOU learned that, not the human. Rewrite these memories so the human is the subject (e.g., "Sufyan is my creator"). Do NOT use "I" or "me" in this section.
6. THE MIGRATION: If you see an entry in this section that is purely an emotional state or a personality trait (e.g., "The user feels flattered..."), you MUST delete it from the [FACTS] section and move it to the [FEELINGS] section!
7. LENGTH LIMIT: EACH numbered entry CAN be a maximum of 75 characters long. Condense any long facts!

[FEELINGS]
1. Review your current emotional states. Delete any feelings you no longer hold, UPDATE/CHANGE any feelings that have evolved based on recent events, and delete any entries that simply repeat your base personality (e.g. "I am competitive").
2. Only keep specific emotional reactions tied to distinct events.
3. STRICT FIRST-PERSON POV: If you migrate feelings from the FACTS database, you MUST rewrite them using "I", "me", and "my" (e.g., "I feel a strong connection..."). Do NOT use "The user feels..." to describe your own feelings!
4. Use bullet points (-).
5. LENGTH LIMIT: EACH bullet point CAN be a maximum of 75 characters long. Condense any run-on paragraphs!
CRITICAL FORMATTING RULES:
- NEVER write `// Deleted` or ANY code comments in the diary! If an entry is deleted, completely erase the line from existence.
- Keep the exact same numbering for the [FACTS] you keep. Do NOT renumber them!

Your Current Global Information Diary (FACTS):
{global_diary if global_diary else "[Diary is currently empty]"}

Your Current Feelings Diary:
{global_feelings if global_feelings else "[Feelings Diary is empty]"}

AT THE VERY END, you MUST output a [CHANGELOG] detailing exactly what you changed."""

    try:
        response = await openrouter_client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4
        )
        audited_text = response.choices[0].message.content.strip()
        
        import re
        parts = re.split(r'\[CHANGELOG\]', audited_text, flags=re.IGNORECASE)
        audited_diaries = parts[0].strip()
        
        facts_match = re.search(r'\[FACTS\](.*?)(\[FEELINGS\]|$)', audited_diaries, re.IGNORECASE | re.DOTALL)
        feelings_match = re.search(r'\[FEELINGS\](.*)', audited_diaries, re.IGNORECASE | re.DOTALL)
        
        new_facts = facts_match.group(1).strip() if facts_match else ""
        new_feelings = feelings_match.group(1).strip() if feelings_match else ""
        
        changelog = "No changes made."
        if len(parts) > 1:
            changelog = parts[1].strip()
            
        with open("audit_logs.txt", "a", encoding="utf-8") as logf:
            import datetime
            logf.write(f"\n--- REEVALUATION CYCLE FOR {channel_id} AT {datetime.datetime.now()} ---\n")
            logf.write(changelog + "\n")
            
        if new_facts:
            save_global_diary(channel_id, new_facts)
        if new_feelings:
            save_global_feelings(channel_id, new_feelings)
            
        print(f"Autonomously audited memory databases for {channel_id}.")
    except Exception as e:
        print(f"Failed to audit memory: {e}")

def inject_game_memory(channel_id, result_text):
    if channel_id in conversation_history:
        notification = f"[SYSTEM NOTIFICATION: {result_text}]"
        conversation_history[channel_id].append({"role": "system", "content": notification})
        name = active_conversations.get(channel_id, f"woolgirl chat {datetime.date.today().strftime('%Y-%m-%d')}")
        save_conversation(channel_id, name)
        bot.loop.create_task(compress_memory(channel_id))

async def force_ai_response(channel, system_prompt_addition, bypass_sleep=False):
    import re
    is_bargaining = channel.id in bargaining_states
    
    target_history = bargaining_states[channel.id] if is_bargaining else conversation_history.get(channel.id)
    if target_history is None:
        conversation_history[channel.id] = []
        target_history = conversation_history[channel.id]
    
    target_history.append({"role": "system", "content": f"[SYSTEM NOTIFICATION: {system_prompt_addition}]"})
    
    async with channel.typing():
        try:
            client = get_active_client()
            
            payload_history = list(target_history)
            if len(payload_history) > 0 and payload_history[0].get("role") != "system":
                payload_history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
                
            current_time = datetime.datetime.now().strftime("%I:%M %p")
            current_date = datetime.date.today().strftime("%B %d, %Y")
            if channel.id in user_states:
                state_data = user_states[channel.id]
                current_state = state_data["state"]
                energy = state_data["energy"]
                missed = state_data["missed_messages"]
                
                state_injection = f"\n\n[CURRENT STATE: {current_state} | ENERGY: {energy}%]"
                if current_state == "Tired":
                    state_injection += " You are exhausted, yawning, and sleepy. You want to go to sleep."
                if missed > 0:
                    state_injection += f"\n[MISSED MESSAGES BUFFER: You just woke up at {current_time}. While you were asleep, the user tried to text you {missed} times. You can react to this.]"
                    if current_state != "Asleep":
                        state_data["missed_messages"] = 0
                        save_user_states()
                        
                time_injection = f"\n\n[CURRENT REAL-WORLD TIME: {current_time} | DATE: {current_date}]{state_injection}"
            else:
                time_injection = f"\n\n[CURRENT REAL-WORLD TIME: {current_time} | DATE: {current_date}]"
            
            diary = get_global_diary(channel.id)
            feelings = get_global_feelings(channel.id)
            
            sys_content = f"{SYSTEM_PROMPT}{time_injection}"
            if diary:
                sys_content += f"\n\n[GLOBAL INFORMATION DIARY (FACTS ONLY)]\n{diary}"
            if feelings:
                sys_content += f"\n\n[FEELINGS DIARY (EMOTIONS & OPINIONS)]\n{feelings}"
                
            payload_history[0] = {"role": "system", "content": sys_content}
                
            if active_api_provider == "groq":
                payload_history = sanitize_history_for_groq(payload_history)
                
            response = await client.chat.completions.create(
                model=active_model_name,
                messages=payload_history,
                max_tokens=250,
                temperature=0.9
            )
            ai_response = response.choices[0].message.content
            
            print(f"\n=== BACKGROUND / SYSTEM EVENT ===")
            print(f"PROMPT: {prompt}")
            print(f"--- WOOLGIRL'S RAW INTERNAL THOUGHTS ---")
            print(f"{ai_response}")
            print(f"=======================================\n")
            
            ai_response = re.sub(r'\[START_GAME:\s*(.+?)\]', '', ai_response, flags=re.IGNORECASE).strip()
            
            cmd_match = re.search(r'\[COMMAND:\s*([a-zA-Z_]+)(?:\s+(.*))?', ai_response, re.IGNORECASE | re.DOTALL)
            sys_command = None
            sys_args = None
            
            if cmd_match:
                sys_command = cmd_match.group(1).strip().lower()
                sys_args = cmd_match.group(2).strip() if cmd_match.group(2) else None
                if sys_args:
                    sys_args = sys_args.rstrip('])')
                ai_response = re.sub(r'\[COMMAND:\s*([a-zA-Z_]+)(?:\s+(.*))?', '', ai_response, flags=re.IGNORECASE | re.DOTALL).strip()
            
            target_history.append({"role": "assistant", "content": response.choices[0].message.content})
            
            if not is_bargaining:
                if len(conversation_history[channel.id]) > MAX_HISTORY + 1:
                    bot.loop.create_task(compress_memory(channel.id))
                name = active_conversations.get(channel.id, f"woolgirl chat {datetime.date.today().strftime('%Y-%m-%d')}")
                save_conversation(channel.id, name)
            
            if ai_response:
                chunks = [ai_response[i:i+1900] for i in range(0, len(ai_response), 1900)]
                for chunk in chunks:
                    await channel.send(chunk)
            
            if sys_command:
                await handle_system_command(sys_command, sys_args, channel, channel.id)
        except Exception as e:
            print(f"Error forcing AI response: {e}")

async def perform_coinflip(channel):
    outcome = random.choice(["Heads", "Tails"])
    await channel.send(f"I flipped a coin and it landed on {outcome}. Now stop making me do manual labor for you, idiot!")
    inject_game_memory(channel.id, f"You just flipped a coin for the user and it landed on {outcome}.")

# --- Rock Paper Scissors Classes ---
class RPSButton(discord.ui.Button):
    def __init__(self, choice_name, emoji):
        super().__init__(style=discord.ButtonStyle.primary, label=choice_name, emoji=emoji)
        self.choice_name = choice_name

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if interaction.user != view.player:
            await interaction.response.send_message("Wait your turn, idiot! This is my game with someone else!", ephemeral=True)
            return

        for child in view.children:
            child.disabled = True
            
        bot_choice = random.choice(["Rock", "Paper", "Scissors"])
        user_choice = self.choice_name
        
        if user_choice == bot_choice:
            result = "It's a tie... don't copy me, weirdo!"
            inject_game_memory(interaction.channel_id, "You just tied a game of Rock-Paper-Scissors with the user. You both chose the same thing. Tell them to stop copying you!")
        elif (user_choice == "Rock" and bot_choice == "Scissors") or \
             (user_choice == "Paper" and bot_choice == "Rock") or \
             (user_choice == "Scissors" and bot_choice == "Paper"):
            result = "You won... you just got lucky this time! Don't get cocky!"
            inject_game_memory(interaction.channel_id, f"The user just beat you at Rock-Paper-Scissors! They chose {user_choice} and you chose {bot_choice}. Be extremely angry and defensive about losing!")
        else:
            result = "I win! You really thought you could beat me? How pathetic!"
            inject_game_memory(interaction.channel_id, f"You just won a game of Rock-Paper-Scissors against the user! They chose {user_choice} and you chose {bot_choice}. Gloat about your victory!")
            
        await interaction.response.edit_message(view=view)
        await interaction.followup.send(f"You chose {user_choice}, and I pick {bot_choice}! {result}")

class RPSView(discord.ui.View):
    def __init__(self, player):
        super().__init__()
        self.player = player
        self.add_item(RPSButton("Rock", "🪨"))
        self.add_item(RPSButton("Paper", "📄"))
        self.add_item(RPSButton("Scissors", "✂️"))

# --- Tic Tac Toe Classes ---
class TicTacToeButton(discord.ui.Button):
    def __init__(self, x, y):
        super().__init__(style=discord.ButtonStyle.secondary, label='\u200b', row=y)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        
        # Ensure only the original player can interact
        if interaction.user != view.player:
            await interaction.response.send_message("This isn't your game, idiot!", ephemeral=True)
            return

        if view.board[self.y][self.x] != 0:
            await interaction.response.send_message("Are you blind? That spot is taken!", ephemeral=True)
            return

        # Player move
        view.board[self.y][self.x] = view.X
        self.style = discord.ButtonStyle.success
        self.label = 'X'
        self.disabled = True
        
        if view.check_winner(view.X):
            view.disable_all()
            await interaction.response.edit_message(content=f"You won... Y-you must have cheated! There's no way a baka like you beat me!", view=view)
            inject_game_memory(interaction.channel_id, "The user just beat you at Tic-Tac-Toe! Be extremely angry, accuse them of cheating, and complain about losing!")
            return
        elif view.is_board_full():
            view.disable_all()
            await interaction.response.edit_message(content="It's a tie. What a waste of my time.", view=view)
            inject_game_memory(interaction.channel_id, "You just played Tic-Tac-Toe with the user and it ended in a tie. Tell them they are a waste of time.")
            return
            
        # Bot move
        bot_moved = view.make_bot_move()
        if bot_moved:
            if view.check_winner(view.O):
                view.disable_all()
                await interaction.response.edit_message(content="Hah! I win! You really thought you could beat me? Pathetic!", view=view)
                inject_game_memory(interaction.channel_id, "You just beat the user at Tic-Tac-Toe! Gloat about your victory and call them an idiot for thinking they could win!")
                return
            elif view.is_board_full():
                view.disable_all()
                await interaction.response.edit_message(content="It's a tie. You're barely even a challenge.", view=view)
                inject_game_memory(interaction.channel_id, "You just played Tic-Tac-Toe with the user and it ended in a tie. Tell them they are a waste of time.")
                return

        await interaction.response.edit_message(content="Your turn, slowpoke.", view=view)

class TicTacToeView(discord.ui.View):
    X = -1
    O = 1

    def __init__(self, player):
        super().__init__()
        self.player = player
        self.board = [[0, 0, 0] for _ in range(3)]
        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y))

    def check_winner(self, player):
        for i in range(3):
            if all(self.board[i][j] == player for j in range(3)): return True
            if all(self.board[j][i] == player for j in range(3)): return True
        if all(self.board[i][i] == player for i in range(3)): return True
        if all(self.board[i][2-i] == player for i in range(3)): return True
        return False

    def is_board_full(self):
        return all(self.board[y][x] != 0 for y in range(3) for x in range(3))

    def disable_all(self):
        for child in self.children:
            child.disabled = True

    def make_bot_move(self):
        empty_spots = [(x, y) for y in range(3) for x in range(3) if self.board[y][x] == 0]
        if not empty_spots:
            return False
            
        # Try to win
        for x, y in empty_spots:
            self.board[y][x] = self.O
            if self.check_winner(self.O):
                self._update_button(x, y, self.O)
                return True
            self.board[y][x] = 0
            
        # Try to block
        for x, y in empty_spots:
            self.board[y][x] = self.X
            if self.check_winner(self.X):
                self.board[y][x] = self.O
                self._update_button(x, y, self.O)
                return True
            self.board[y][x] = 0

        # Random
        x, y = random.choice(empty_spots)
        self.board[y][x] = self.O
        self._update_button(x, y, self.O)
        return True

    def _update_button(self, x, y, player):
        for child in self.children:
            if hasattr(child, 'x') and child.x == x and child.y == y:
                child.style = discord.ButtonStyle.danger
                child.label = 'O'
                child.disabled = True
                break
# --- End Tic Tac Toe ---

async def handle_system_command(command, args, channel, channel_id):
    if command == "all_conversations":
        if not isinstance(channel, discord.DMChannel):
            await channel.send("Are you stupid? Save files are only for private DMs! In a server, we just talk normally.")
            return
        save_list = get_saved_conversations(channel_id)
        if not save_list:
            await channel.send("You haven't saved any memories yet, dummy!")
        else:
            saves_str = "\n".join([f"- {s}" for s in save_list])
            view = DeleteSaveView(channel_id, save_list)
            await channel.send(f"Here are your saved memories. Select one below if you want me to delete it:\n{saves_str}", view=view)
            
    elif command == "new":
        if not isinstance(channel, discord.DMChannel):
            await channel.send("Are you stupid? Save files are only for private DMs! In a server, we just talk normally.")
            return
        name = args if args else f"woolgirl chat {datetime.date.today().strftime('%Y-%m-%d')}"
        had_active = channel_id in active_conversations
        conversation_history[channel_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        active_conversations[channel_id] = name
        save_conversation(channel_id, name)
        
        if had_active:
            await channel.send(f"Fine, I wiped my memory. We are starting over in a new save called **'{name}'**. Don't be weird this time!")
        else:
            await channel.send(f"Fine, I created a new save called **'{name}'** for us. Don't be weird!")
            
    elif command == "load":
        if not isinstance(channel, discord.DMChannel):
            await channel.send("Are you stupid? Save files are only for private DMs! In a server, we just talk normally.")
            return
        name = args
        if not name:
            await channel.send("You didn't give me a name to load, baka!")
            return
            
        if load_conversation(channel_id, name):
            active_conversations[channel_id] = name
            await channel.send(f"I loaded the memory **'{name}'**. Here is what happened... don't make me repeat it again!")
            
            history = conversation_history[channel_id]
            transcript = ""
            for msg in history:
                if msg["role"] == "system": continue
                if msg["role"] == "user": transcript += f"**{msg['content']}**\n"
                elif msg["role"] == "assistant": transcript += f"**Tsundere:** {msg['content']}\n\n"
            
            if transcript:
                chunks = [transcript[i:i+1900] for i in range(0, len(transcript), 1900)]
                for chunk in chunks:
                    await channel.send(chunk)
        else:
            await channel.send(f"Are you blind? There is no save file named **'{name}'**! Ask to see all saves if you forgot!")
            
    elif command == "reset":
        name = active_conversations.get(channel_id, f"woolgirl chat {datetime.date.today().strftime('%Y-%m-%d')}")
        
        # Keep the save file, but wipe all message history back to the original System Prompt
        conversation_history[channel_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        save_conversation(channel_id, name)
            
    elif command == "cancel_forget":
        if channel_id in bargaining_states:
            del bargaining_states[channel_id]
            await channel.send("*[SYSTEM: You yielded. The temporary bargaining state has ended, and she successfully kept her memory. You have returned to the normal active chat.]*")

    elif command == "confirm_forget":
        number = args
        diary_entries = get_global_diary(channel_id)
        if diary_entries and number:
            lines = diary_entries.split('\n')
            new_lines = []
            deleted = False
            
            import re
            target_pattern = re.compile(rf"^{number}\.")
            for line in lines:
                if target_pattern.match(line.strip()):
                    deleted = True
                else:
                    new_lines.append(line)
                    
            if deleted:
                updated_diary = '\n'.join(new_lines).strip()
                save_global_diary(channel_id, updated_diary)
                
                if channel_id in conversation_history:
                    conversation_history[channel_id].append({
                        "role": "system", 
                        "content": f"[SYSTEM NOTIFICATION: Memory #{number} has been permanently erased from your Global Diary as requested. Act accordingly.]"
                    })

        if channel_id in bargaining_states:
            del bargaining_states[channel_id]
            await channel.send("*[SYSTEM: She yielded. The memory has been permanently erased, and the temporary bargaining state has ended. You have returned to the normal active chat.]*")
        elif isinstance(channel, discord.DMChannel):
            await channel.send("I erased my internal memory! But since we are in a private DM, Discord physically won't let me delete your messages for you. You'll have to clear the screen yourself, idiot!")
        else:
            await channel.purge(limit=100)
            await channel.send("I erased my memory and deleted the recent chat history. Happy now?!", delete_after=10)

    elif command == "set_sleep_timer":
        try:
            hours = float(args)
        except:
            hours = 6.0
            
        if channel_id in user_states:
            import time
            state_data = user_states[channel_id]
            state_data["state"] = "Asleep"
            state_data["wake_up_time"] = time.time() + (hours * 3600)
            state_data["missed_messages"] = 0
            save_user_states()
            print(f"User {channel_id} went to sleep for {hours} hours.")
            
            if channel_id in conversation_history:
                conversation_history[channel_id].append({
                    "role": "system",
                    "content": f"[SYSTEM NOTIFICATION: You just fell asleep for {hours} hours. You are currently ASLEEP.]"
                })
                name = active_conversations.get(channel_id, f"woolgirl chat {datetime.date.today().strftime('%Y-%m-%d')}")
                save_conversation(channel_id, name)

    elif command == "set_energy":
        try:
            amt = int(args)
            if channel_id in user_states:
                user_states[channel_id]["energy"] = max(0, min(100, amt))
                save_user_states()
        except: pass
        
    elif command == "set_state":
        state = args.capitalize()
        if state in ["Awake", "Tired", "Asleep"] and channel_id in user_states:
            user_states[channel_id]["state"] = state
            save_user_states()
            
    elif command == "generate_pdf":
        # Remove any leading pipes from args just in case the AI included one
        clean_args = args.lstrip("|").strip()
        parts = clean_args.split("|", 1)
        
        raw_topic = parts[0].strip() if len(parts) > 0 else "document"
        if not raw_topic: raw_topic = "document"
        
        # Prevent massive topics from crashing Discord's 2000 char limit
        topic = raw_topic[:50] + "..." if len(raw_topic) > 50 else raw_topic
        
        content = parts[1].strip() if len(parts) > 1 else raw_topic
        
        await channel.send(f"*[SYSTEM: Compiling your markdown into a physical PDF document regarding '{topic}'...]*")
        
        try:
            import markdown
            import re
            import aiohttp
            import os
            import uuid
            from fpdf import FPDF
            
            img_pattern = re.compile(r'!\[.*?\]\((.*?)\)')
            urls = img_pattern.findall(content)
            temp_files = []
            
            async with aiohttp.ClientSession() as session:
                for url in urls:
                    try:
                        async with session.get(url, timeout=5) as resp:
                            if resp.status == 200:
                                ext = url.split('.')[-1].lower()
                                if ext not in ['jpg', 'jpeg', 'png', 'gif']:
                                    ext = 'jpg'
                                temp_filename = f"temp_img_{uuid.uuid4().hex}.{ext}"
                                with open(temp_filename, 'wb') as f:
                                    f.write(await resp.read())
                                temp_files.append(temp_filename)
                                content = content.replace(url, temp_filename)
                    except Exception as e:
                        print(f"Failed to download image {url}: {e}")
                        
            html_content = markdown.markdown(content)
            
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("helvetica", size=12)
            pdf.write_html(html_content)
            
            filename_safe = re.sub(r'[^a-zA-Z0-9_\-]', '', topic.replace(' ', '_'))[:30]
            if not filename_safe: filename_safe = "document"
            filename = f"{filename_safe}.pdf"
            
            pdf.output(filename)
            
            await channel.send(f"Here is your stupid document about '{topic}'! Don't ask me to do this again!", file=discord.File(filename))
            
            os.remove(filename)
            for tmp in temp_files:
                if os.path.exists(tmp):
                    os.remove(tmp)
        except Exception as e:
            await channel.send(f"*[SYSTEM ERROR: Failed to generate PDF: {e}]*")

async def tamagotchi_watchdog():
    import time
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = time.time()
        for channel_id, state_data in list(user_states.items()):
            channel = bot.get_channel(channel_id)
            if not channel:
                try:
                    channel = await bot.fetch_channel(channel_id)
                except:
                    continue
            if not channel: continue
            
            c_state = state_data.get("state", "Awake")
            last_msg = state_data.get("last_message_time", now)
            last_audit = state_data.get("last_audit_time", now)
            
            # Pure 5-hour background audit timer
            if now - last_audit > 18000:
                bot.loop.create_task(reevaluate_memory(channel_id))
                state_data["last_audit_time"] = now
                save_user_states()            
            if c_state == "Tired":
                if now - last_msg > 600:
                    prompt = "You have been exhausted and tired for 10 minutes. The user hasn't messaged you. You are now falling asleep. Output [COMMAND: set_sleep_timer <hours>] to decide exactly how many hours you want to sleep (The golden number is 6, and your absolute MAXIMUM limit is 8 hours). Do NOT output anything else."
                    bot.loop.create_task(force_ai_response(channel, prompt, bypass_sleep=True))
                    state_data["last_message_time"] = now
                    save_user_states()
            
            elif c_state == "Asleep":
                wake_time = state_data.get("wake_up_time", 0)
                if now > wake_time and wake_time > 0:
                    state_data["state"] = "Awake"
                    state_data["energy"] = 100
                    state_data["last_message_time"] = now
                    save_user_states()
                    
                    prompt = "You just woke up from a long sleep. Your energy is fully restored to 100%. Check your MISSED MESSAGES buffer if you have one, and send the user a message now that you are awake."
                    bot.loop.create_task(force_ai_response(channel, prompt, bypass_sleep=True))
                    
            elif c_state == "Awake":
                target_idle = state_data.get("idle_ping_target", 18000)
                if now - last_msg > target_idle:
                    prompt = "You haven't heard from the user in a long time. Send them a spontaneous text message checking in on them (tsundere style). Do not mention that you were prompted to do this."
                    bot.loop.create_task(force_ai_response(channel, prompt, bypass_sleep=True))
                    state_data["last_message_time"] = now
                    state_data["idle_ping_target"] = random.randint(3, 7) * 3600
                    save_user_states()
        await asyncio.sleep(60)

async def update_discord_status():
    await bot.wait_until_ready()
    awake_activities = ["Crazy Revolver Cards", "Watching you (don't flatter yourself)", "Listening to Lo-Fi", "Ignoring you"]
    while not bot.is_closed():
        global_state = "Awake"
        if user_states:
            latest_user = max(user_states.values(), key=lambda x: x.get("last_message_time", 0))
            global_state = latest_user.get("state", "Awake")
            
        if global_state == "Awake":
            activity_name = random.choice(awake_activities)
            await bot.change_presence(activity=discord.Game(name=activity_name), status=discord.Status.online)
        elif global_state == "Tired":
            await bot.change_presence(activity=discord.Game(name="Being tired..."), status=discord.Status.idle)
        elif global_state == "Asleep":
            await bot.change_presence(activity=discord.Game(name="Sleeping (Zzz...)"), status=discord.Status.dnd)
            
        await asyncio.sleep(600)

@bot.event
async def on_ready():
    bot.loop.create_task(tamagotchi_watchdog())
    bot.loop.create_task(update_discord_status())
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('Tsundere bot is hooked up to the internet for GIFs!')
    
    # Start a dummy web server so cloud hosts (like Render) don't kill the bot
    app = web.Application()
    app.router.add_get('/', lambda request: web.Response(text="Woolgirl is awake and annoyed!"))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Dummy web server started on port {port}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        user_msg = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        channel_id = message.channel.id
        
        is_dm = isinstance(message.channel, discord.DMChannel)
        has_active_save = channel_id in active_conversations and channel_id in conversation_history
        
        is_bargaining = channel_id in bargaining_states
        target_history = bargaining_states[channel_id] if is_bargaining else conversation_history.setdefault(channel_id, [{"role": "system", "content": SYSTEM_PROMPT}])

        if channel_id not in user_states:
            import time
            user_states[channel_id] = {
                "energy": 100,
                "state": "Awake",
                "missed_messages": 0,
                "last_message_time": time.time(),
                "wake_up_time": 0,
                "idle_ping_target": random.randint(3, 7) * 3600
            }
            save_user_states()

        state_data = user_states[channel_id]
        
        # Intercept messages if asleep
        if state_data["state"] == "Asleep" and not is_bargaining:
            state_data["missed_messages"] += 1
            save_user_states()
            
            sleep_msgs = [
                "Zzz... *mumbles* no, baka... leave my pudding alone...",
                "*soft snoring sounds* (She is deeply asleep)",
                "Zzz... five more minutes...",
                "*She is dead to the world, drooling slightly on her desk.*",
                "Zzz... idiot...",
                "(She doesn't respond. She's fast asleep.)"
            ]
            sleep_msg = random.choice(sleep_msgs)
            
            # Send as a normal text message with a Tenor link so Discord natively unfurls the GIF
            gif_link = "https://tenor.com/view/anime-sleep-gif-25626372"
            await message.channel.send(f"{sleep_msg}\n{gif_link}")
            return

        import time
        state_data["last_message_time"] = time.time()
        if state_data["state"] != "Asleep":
            state_data["energy"] = max(0, state_data["energy"] - 1)
            if state_data["energy"] < 20 and state_data["state"] == "Awake":
                state_data["state"] = "Tired"
            save_user_states()

        # Check for images
        if message.attachments:
            img_url = message.attachments[0].url
            if active_api_provider == "openrouter":
                content_payload = [
                    {"type": "text", "text": f"{message.author.display_name} (@{message.author.name}): {user_msg}"},
                    {"type": "image_url", "image_url": {"url": img_url}}
                ]
                target_history.append({"role": "user", "content": content_payload})
            else:
                target_history.append({"role": "user", "content": f"{message.author.display_name} (@{message.author.name}): {user_msg}\n\n[USER ATTACHED AN IMAGE. BUT YOU ARE RUNNING ON GROQ AND CANNOT SEE IT! Yell at the user for sending you a picture when you don't have your glasses on!]"})
        else:
            target_history.append({"role": "user", "content": f"{message.author.display_name} (@{message.author.name}): {user_msg}"})
        
        if not is_bargaining and len(conversation_history[channel_id]) > MAX_HISTORY + 1:
            bot.loop.create_task(compress_memory(channel_id))

        async with message.channel.typing():
            try:
                client = get_active_client()
                
                payload_history = list(target_history)
                current_time = datetime.datetime.now().strftime("%I:%M %p")
                current_date = datetime.date.today().strftime("%B %d, %Y")
                
                current_state = state_data["state"]
                energy = state_data["energy"]
                missed = state_data["missed_messages"]
                
                state_injection = f"\n\n[CURRENT STATE: {current_state} | ENERGY: {energy}%]"
                if current_state == "Tired":
                    state_injection += " You are exhausted, yawning, and sleepy. You want to go to sleep."
                if missed > 0:
                    state_injection += f"\n[MISSED MESSAGES BUFFER: You just woke up at {current_time}. While you were asleep, the user tried to text you {missed} times. You can react to this.]"
                    if current_state != "Asleep":
                        state_data["missed_messages"] = 0
                        save_user_states()
                
                time_injection = f"\n\n[CURRENT REAL-WORLD TIME: {current_time} | DATE: {current_date}]{state_injection}"
                
                diary = get_global_diary(channel_id)
                feelings = get_global_feelings(channel_id)
                
                sys_content = f"{SYSTEM_PROMPT}{time_injection}"
                if diary:
                    sys_content += f"\n\n[GLOBAL INFORMATION DIARY (FACTS ONLY)]\n{diary}"
                if feelings:
                    sys_content += f"\n\n[FEELINGS DIARY (EMOTIONS & OPINIONS)]\n{feelings}"
                    
                payload_history[0] = {"role": "system", "content": sys_content}
                    
                if active_api_provider == "groq":
                    payload_history = sanitize_history_for_groq(payload_history)

                # First LLM call
                response = await client.chat.completions.create(
                    model=active_model_name, 
                    messages=payload_history,
                    tools=BOT_TOOLS,
                    tool_choice="auto"
                )
                
                response_msg = response.choices[0].message
                
                # Check for Tool Calls (Web Browsing)
                if response_msg.tool_calls:
                    print("Tool call detected!")
                    tool_call_dicts = []
                    for t in response_msg.tool_calls:
                        tool_call_dicts.append({
                            "id": t.id,
                            "type": "function",
                            "function": {
                                "name": t.function.name,
                                "arguments": t.function.arguments
                            }
                        })
                    
                    target_history.append({"role": "assistant", "tool_calls": tool_call_dicts, "content": response_msg.content or ""})
                    payload_history.append({"role": "assistant", "tool_calls": tool_call_dicts, "content": response_msg.content or ""})
                    
                    for tool_call in response_msg.tool_calls:
                        tool_result = await execute_tool_call(tool_call)
                        target_history.append({"role": "tool", "name": tool_call.function.name, "tool_call_id": tool_call.id, "content": tool_result})
                        payload_history.append({"role": "tool", "name": tool_call.function.name, "tool_call_id": tool_call.id, "content": tool_result})
                    
                    # Second LLM call with search results
                    response = await client.chat.completions.create(
                        model=active_model_name,
                        messages=payload_history
                    )
                    response_msg = response.choices[0].message
                
                ai_response = response.choices[0].message.content
                
                print(f"\n=== NEW MESSAGE FROM {message.author.display_name} ===")
                print(f"USER: {user_msg}")
                print(f"--- WOOLGIRL'S RAW INTERNAL THOUGHTS ---")
                print(f"{ai_response}")
                print(f"=======================================================\n")
                
                # Parse for the GIF search tag
                gif_match = re.search(r'[\[\(]GIF:\s*(.+?)[\]\)]', ai_response, re.IGNORECASE)
                file_to_send = None
                
                if gif_match:
                    search_query = gif_match.group(1).strip()
                    if "anime girl" not in search_query.lower():
                        search_query = "anime girl " + search_query
                    search_query = search_query.replace(' ', '-')
                    
                    # Remove the tag from the text sent to Discord
                    ai_response = re.sub(r'[\[\(]GIF:\s*(.+?)[\]\)]', '', ai_response, flags=re.IGNORECASE).strip()
                    
                    # Fetch GIF from internet
                    async with aiohttp.ClientSession() as session:
                        url = f"https://tenor.com/search/{search_query}-gifs"
                        async with session.get(url, headers={'User-Agent': 'Mozilla/5.0'}) as resp:
                            if resp.status == 200:
                                html = await resp.text()
                                gifs = list(set(re.findall(r'https://media1\.tenor\.com/m/[a-zA-Z0-9_-]+/[^"]+\.gif', html)))
                                if not gifs:
                                    gifs = list(set(re.findall(r'https://media\.tenor\.com/[^"]+\.gif', html)))
                                
                                if gifs:
                                    gif_url = random.choice(gifs[:3])
                                    async with session.get(gif_url) as gif_resp:
                                        if gif_resp.status == 200:
                                            gif_bytes = await gif_resp.read()
                                            file_to_send = discord.File(io.BytesIO(gif_bytes), filename="reaction.gif")
                
                game_match = re.search(r'\[START_GAME:\s*(.+?)\]', ai_response, re.IGNORECASE)
                game_to_start = None
                
                if game_match:
                    game_to_start = game_match.group(1).strip()
                    ai_response = re.sub(r'\[START_GAME:\s*(.+?)\]', '', ai_response, flags=re.IGNORECASE).strip()

                cmd_match = re.search(r'\[COMMAND:\s*([a-zA-Z_]+)(?:\s+(.*))?', ai_response, re.IGNORECASE | re.DOTALL)
                sys_command = None
                sys_args = None
                
                if cmd_match:
                    sys_command = cmd_match.group(1).strip().lower()
                    sys_args = cmd_match.group(2).strip() if cmd_match.group(2) else None
                    if sys_args:
                        sys_args = sys_args.rstrip('])')
                    ai_response = re.sub(r'\[COMMAND:\s*([a-zA-Z_]+)(?:\s+(.*))?', '', ai_response, flags=re.IGNORECASE | re.DOTALL).strip()
                
                if sys_command:
                    print(f"[SYSTEM COMMAND DETECTED]: {sys_command} | ARGS: {sys_args}")

                if is_dm and not has_active_save and not sys_command and not is_bargaining:
                    await message.reply("Hmph! We don't have an active save file right now! You need to use `/new` to create a new conversation, or `/all_conversations` to load an old one before we can talk.")
                    target_history.pop()
                    return

                # Add AI's raw response to history (so it remembers its tags)
                target_history.append({"role": "assistant", "content": response.choices[0].message.content})
                
                # Send the response back to Discord
                if ai_response:
                    chunks = [ai_response[i:i+1900] for i in range(0, len(ai_response), 1900)]
                    if file_to_send:
                        await message.reply(chunks[0], file=file_to_send)
                        for chunk in chunks[1:]:
                            await message.channel.send(chunk)
                    else:
                        await message.reply(chunks[0])
                        for chunk in chunks[1:]:
                            await message.channel.send(chunk)
                    
                # Trigger the game AFTER sending the AI's dialogue
                if game_to_start:
                    if "tictactoe" in game_to_start:
                        await message.channel.send("Alright, Tic-Tac-Toe! Don't cry when you lose!", view=TicTacToeView(message.author))
                    elif "rps" in game_to_start:
                        await message.channel.send("Rock, Paper, Scissors! Make your choice, slowpoke!", view=RPSView(message.author))
                    elif "coinflip" in game_to_start:
                        await perform_coinflip(message.channel)
                    elif "crc" in game_to_start.lower():
                        from crc_game import CRCView, generate_crc_board
                        parts = [p.strip() for p in game_to_start.split('|')]
                        player_name = parts[1] if len(parts) > 1 else message.author.display_name
                        try:
                            hp_count = int(parts[2]) if len(parts) > 2 else 3
                        except:
                            hp_count = 3
                        view = CRCView(message.author, inject_game_memory, player_name=player_name, max_hp=hp_count, trigger_ai_callback=force_ai_response)
                        img_bytes = generate_crc_board(view.player_hp, view.opp_hp, view.player_cards, view.opp_cards, opp_hidden=True, player_name=player_name)
                        file = discord.File(img_bytes, filename="board.png")
                        embed = discord.Embed(title="Crazy Revolver Cards", description=f"```yaml\n> {player_name.upper()} challenged Woolgirl!\n> Game starts with {hp_count} HP.\n```", color=0xD4AF37)
                        embed.set_image(url="attachment://board.png")
                        await message.channel.send("Oh? You think you can beat me at Crazy Revolver Cards? Deal your cards, baka!", embed=embed, file=file, view=view)
                        
                # Trigger system commands AFTER sending the AI's dialogue
                if sys_command:
                    await handle_system_command(sys_command, sys_args, message.channel, channel_id)
                
            except Exception as e:
                print(f"Error calling APIs: {e}")
                excuses = [
                    "Wait, baka! I'm busy right now, my mom is calling me!",
                    "Hold on an idiot second, I'm doing something important!",
                    "Ugh, don't rush me! Can't you see I'm busy?!",
                    "I'm ignoring you for a minute because you're annoying!",
                    "Give me a minute, baka! It's not like I'm sitting around waiting for your messages!"
                ]
                await message.reply(f"{random.choice(excuses)}\n\n`[SYSTEM DEBUG ERROR: {e}]`")
                
        # Auto-save after responding (only if not in a temporary state)
        if is_dm and not is_bargaining:
            save_conversation(channel_id, active_conversations.get(channel_id, f"woolgirl chat {datetime.date.today().strftime('%Y-%m-%d')}"))

    await bot.process_commands(message)

@bot.tree.command(name="new", description="Wipes the chat history and starts a new auto-saving conversation.")
@app_commands.describe(name="The name to save this new conversation under (optional)")
async def new(interaction: discord.Interaction, name: str = None):
    if not isinstance(interaction.channel, discord.DMChannel):
        await interaction.response.send_message("Are you stupid? Save files are only for private DMs! In a server, we just talk normally.", ephemeral=True)
        return
    if not name:
        name = f"woolgirl chat {datetime.date.today().strftime('%Y-%m-%d')}"
        
    channel_id = interaction.channel_id
    had_active = channel_id in active_conversations
    conversation_history[channel_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    active_conversations[channel_id] = name
    save_conversation(channel_id, name)
    
    if had_active:
        await interaction.response.send_message(f"Fine, I wiped my memory. We are starting over in a new save called **'{name}'**. Don't be weird this time!")
    else:
        await interaction.response.send_message(f"Fine, I created a new save called **'{name}'** for us. Don't be weird!")

@bot.tree.command(name="diary", description="Take a peek at Woolgirl's secret subconscious diaries.")
@app_commands.describe(database="Which database do you want to peek into?")
@app_commands.choices(database=[
    app_commands.Choice(name="Facts Database (Information)", value="facts"),
    app_commands.Choice(name="Feelings Database (Emotions)", value="feelings")
])
async def diary(interaction: discord.Interaction, database: str = "facts"):
    channel_id = interaction.channel_id
    
    if database == "facts":
        diary_entries = get_global_diary(channel_id)
        title = "📖 Woolgirl's Facts Database"
        empty_msg = "My facts database is empty right now!"
    else:
        diary_entries = get_global_feelings(channel_id)
        title = "💖 Woolgirl's Feelings Database"
        empty_msg = "I don't have any feelings right now! Stop snooping!!"
        
    if diary_entries:
        embed = discord.Embed(title=title, description=f"```yaml\n{diary_entries}\n```", color=0xFF69B4)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(empty_msg, ephemeral=True)

@bot.tree.command(name="system_status", description="Check Woolgirl's internal state and logs.")
async def system_status(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    energy = 100
    state = "Awake"
    sleep_info = ""
    if channel_id in user_states:
        energy = user_states[channel_id].get("energy", 100)
        state = user_states[channel_id].get("state", "Awake")
        if state == "Asleep":
            import time
            sleep_until = user_states[channel_id].get("sleep_until", 0)
            remaining = max(0, sleep_until - time.time())
            if remaining > 0:
                hours = int(remaining // 3600)
                minutes = int((remaining % 3600) // 60)
                sleep_info = f"\n**Waking up in:** {hours}h {minutes}m"
            else:
                sleep_info = "\n**Waking up in:** Any minute now..."
        
    logs = "No audit logs found yet."
    try:
        with open("audit_logs.txt", "r", encoding="utf-8") as f:
            full_logs = f.read()
        if len(full_logs) > 1000:
            logs = full_logs[-1000:]
        else:
            logs = full_logs
    except:
        pass
        
    embed = discord.Embed(title="⚙️ System Status", color=0x00FF00)
    embed.add_field(name="Current State", value=f"{state}{sleep_info}", inline=True)
    embed.add_field(name="Energy Level", value=f"{energy}%", inline=True)
    embed.add_field(name="Last Reevaluation Logs", value=f"```\n{logs.strip() if logs.strip() else 'No recent logs.'}\n```", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="forget", description="Force Woolgirl to forget a specific numbered diary entry.")
@app_commands.describe(number="The exact number of the diary entry to delete")
async def forget(interaction: discord.Interaction, number: int):
    channel_id = interaction.channel_id
    diary_entries = get_global_diary(channel_id)
    if not diary_entries:
        await interaction.response.send_message("I don't have any diary entries to forget!", ephemeral=True)
        return
        
    lines = diary_entries.split('\n')
    target_line = None
    
    import re
    target_pattern = re.compile(rf"^{number}\.")
    for line in lines:
        if target_pattern.match(line.strip()):
            target_line = line.strip()
            break
            
    if not target_line:
        await interaction.response.send_message(f"Are you blind? There is no entry numbered {number} in my diary!", ephemeral=True)
        return
        
    class_match = re.search(r'\[(.*?)\]', target_line)
    mem_class = class_match.group(1) if class_match else "Normal"
        
    prompt = f'The user just tried to delete entry #{number} from your Global Diary. The entry is: "{target_line}". You previously classified this memory as [{mem_class}]. Consider this class as a baseline, but remember you have complete free will. Just like a real human, your feelings can change based on recent events or how the user treats you. It is entirely up to you how you react—you can fiercely fight to keep it, reluctantly let it go, or agree to delete it immediately by outputting [COMMAND: confirm_forget {number}]. Do NOT output the command if you are bargaining to keep it.'
    
    await interaction.response.send_message(f"*You attempted to delete memory #{number}. You are now in a temporary bargaining state with her. Let's see how she reacts...*")
    
    bargaining_states[channel_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Trigger AI response in the channel
    bot.loop.create_task(force_ai_response(interaction.channel, prompt))

@bot.tree.command(name="load", description="Loads a past conversation and prints the chat history.")
@app_commands.describe(name="The exact name of the conversation you want to load")
async def load(interaction: discord.Interaction, name: str):
    if not isinstance(interaction.channel, discord.DMChannel):
        await interaction.response.send_message("Are you stupid? Save files are only for private DMs! In a server, we just talk normally.", ephemeral=True)
        return
    channel_id = interaction.channel_id
    await interaction.response.defer()
    
    if load_conversation(channel_id, name):
        active_conversations[channel_id] = name
        await interaction.followup.send(f"I loaded the memory **'{name}'**. Here is what happened... don't make me repeat it again!")
        
        history = conversation_history[channel_id]
        transcript = ""
        
        for msg in history:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                continue
            
            if role == "user":
                transcript += f"**{content}**\n"
            elif role == "assistant":
                transcript += f"**Tsundere:** {content}\n\n"
                
        if transcript:
            # Discord limit is 2000 chars. Split safely.
            chunks = [transcript[i:i+1900] for i in range(0, len(transcript), 1900)]
            for chunk in chunks:
                await interaction.followup.send(chunk)
    else:
        await interaction.followup.send(f"Are you blind? There is no save file named **'{name}'**! Type `/all_conversations` to see them.")

class DeleteSaveView(discord.ui.View):
    def __init__(self, channel_id: int, saves: list):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        
        options = []
        for save in saves[:25]:
            options.append(discord.SelectOption(label=save, description=f"Delete save: {save}"))
            
        if options:
            self.select = discord.ui.Select(placeholder="Select a conversation to delete...", options=options)
            self.select.callback = self.select_callback
            self.add_item(self.select)
            
    async def select_callback(self, interaction: discord.Interaction):
        save_name = self.select.values[0]
        safe_name = get_safe_filename(save_name)
        save_path = f"saves/{self.channel_id}_{safe_name}.json"
        try:
            if os.path.exists(save_path):
                os.remove(save_path)
                
                # Clear active tracking if they deleted the currently active save
                if self.channel_id in active_conversations and active_conversations[self.channel_id] == save_name:
                    del active_conversations[self.channel_id]
                    
                await interaction.response.send_message(f"Hmph. I permanently deleted the memory **'{save_name}'**. I hope you didn't need that!", ephemeral=True)
                
                self.select.options = [opt for opt in self.select.options if opt.label != save_name]
                if not self.select.options:
                    self.remove_item(self.select)
                
                await interaction.message.edit(view=self)
            else:
                await interaction.response.send_message("That memory doesn't exist anyway, dummy!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error deleting save: {e}", ephemeral=True)

@bot.tree.command(name="all_conversations", description="Shows all the conversations you've saved and lets you delete them.")
async def all_conversations(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.DMChannel):
        await interaction.response.send_message("Are you stupid? Save files are only for private DMs! In a server, we just talk normally.", ephemeral=True)
        return
    channel_id = interaction.channel_id
    save_list = get_saved_conversations(channel_id)
    if not save_list:
        await interaction.response.send_message("You haven't saved any memories yet, dummy!")
    else:
        saves_str = "\n".join([f"- {s}" for s in save_list])
        view = DeleteSaveView(channel_id, save_list)
        await interaction.response.send_message(f"Here are your saved memories. Select one below if you want me to delete it:\n{saves_str}", view=view)

@bot.tree.command(name="reset", description="Erases my memory and deletes the chat history so we can start over.")
async def reset(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    
    name = active_conversations.get(channel_id, f"woolgirl chat {datetime.date.today().strftime('%Y-%m-%d')}")
    
    # Keep the save file, but wipe all message history back to the original System Prompt
    conversation_history[channel_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    save_conversation(channel_id, name)
        
    await interaction.response.defer()
    
    try:
        if isinstance(interaction.channel, discord.DMChannel):
            await interaction.followup.send("I erased my internal memory! But since we are in a private DM, Discord physically won't let me delete your messages for you. You'll have to clear the screen yourself, idiot!")
        else:
            await interaction.channel.purge(limit=100)
            await interaction.followup.send("I erased everything! We are starting over, and you better be less annoying this time!")
    except discord.Forbidden:
        await interaction.followup.send("I tried to delete the messages, but I don't have the 'Manage Messages' permission in this server! (I did erase my internal memory though, so we are starting over!)")
    except Exception as e:
        await interaction.followup.send(f"I erased my internal memory, but I couldn't delete the chat history due to an error: {e}")

@bot.tree.command(name="help", description="Lists all of the things I can do for you.")
async def custom_help(interaction: discord.Interaction):
    help_text = """
**Hmph, you really can't remember anything on your own, can you?**
Fine, here is a list of things you can do. Try not to forget them this time!

**🧠 Memory Commands:**
`/new <name>` - Wipes the chat and starts a new auto-saving conversation.
`/load <name>` - Loads a past conversation.
`/all_conversations` - Shows all the conversations you've saved.
`/reset` - Erases my memory of our current chat so we can start over.

**🎮 Minigames:**
`/tictactoe` - Play a visual game of Tic-Tac-Toe with me.
`/rps` - Play rock-paper-scissors with me.
`/coinflip` - Make me flip a coin for you.
`/crc` - Play Crazy Revolver Cards with me!
"""
    await interaction.response.send_message(help_text.strip())

@bot.tree.command(name="rps", description="Manually starts a game of Rock-Paper-Scissors.")
async def rps(interaction: discord.Interaction):
    await interaction.response.send_message("Rock, Paper, Scissors! Make your choice, slowpoke!", view=RPSView(interaction.user))

@bot.tree.command(name="coinflip", description="Make me flip a coin for you.")
async def coinflip(interaction: discord.Interaction):
    await interaction.response.send_message("Fine, I'll flip a coin for you.")
    await perform_coinflip(interaction.channel)

@bot.tree.command(name="tictactoe", description="Play a visual game of Tic-Tac-Toe with me.")
async def tictactoe(interaction: discord.Interaction):
    await interaction.response.send_message("Oh? You want to play Tic-Tac-Toe? Prepare to lose, idiot!", view=TicTacToeView(interaction.user))

@bot.tree.command(name="crc", description="Play Crazy Revolver Cards with me!")
async def crc(interaction: discord.Interaction):
    from crc_game import CRCView, generate_crc_board
    view = CRCView(interaction.user, inject_game_memory)
    img_bytes = generate_crc_board(view.player_hp, view.opp_hp, view.player_cards, view.opp_cards, opp_hidden=True)
    file = discord.File(img_bytes, filename="board.png")
    await interaction.response.send_message("Oh? You think you can beat me at Crazy Revolver Cards? Deal your cards, baka!", file=file, view=view)

if __name__ == '__main__':
    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_TOKEN is not set in .env file.")
    elif not GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY is not set in .env file.")
    else:
        print("Starting bot...")
        bot.run(DISCORD_TOKEN)
