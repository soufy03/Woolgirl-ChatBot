import os
import random
import re
import json
import datetime
import discord
import aiohttp
import io
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from openai import AsyncOpenAI
from aiohttp import web

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

# Initialize Groq client
ai_client = AsyncOpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY,
)

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

Example:
User: "Can we start a new save called beach episode?"
Woolgirl: "Ugh, fine! I'll wipe my memory and we can start your stupid beach episode. Don't be a creep! [COMMAND: new beach episode]"
"""

# Simple in-memory conversation history
conversation_history = {}
active_conversations = {}
MAX_HISTORY = 10 

# Add these functions to manage saves
os.makedirs("saves", exist_ok=True)

def get_safe_filename(name):
    return re.sub(r'[^a-zA-Z0-9_\- ]', '', name).strip()

def load_conversation(channel_id, name):
    safe_name = get_safe_filename(name)
    filepath = f"saves/{channel_id}_{safe_name}.json"
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            conversation_history[channel_id] = json.load(f)
        return True
    return False

def save_conversation(channel_id, name):
    safe_name = get_safe_filename(name)
    filepath = f"saves/{channel_id}_{safe_name}.json"
    with open(filepath, 'w') as f:
        json.dump(conversation_history.get(channel_id, []), f)

def get_saved_conversations(channel_id):
    prefix = f"{channel_id}_"
    saves = []
    for file in os.listdir("saves"):
        if file.startswith(prefix) and file.endswith(".json"):
            saves.append(file[len(prefix):-5])
    return saves

def inject_game_memory(channel_id, result_text):
    if channel_id in conversation_history:
        notification = f"[SYSTEM NOTIFICATION: {result_text}]"
        conversation_history[channel_id].append({"role": "system", "content": notification})
        if len(conversation_history[channel_id]) > MAX_HISTORY + 1:
            conversation_history[channel_id].pop(1)
        name = active_conversations.get(channel_id, f"woolgirl chat {datetime.date.today().strftime('%Y-%m-%d')}")
        save_conversation(channel_id, name)

async def force_ai_response(channel, system_prompt_addition):
    import re
    if channel.id not in conversation_history:
        conversation_history[channel.id] = []
    
    conversation_history[channel.id].append({"role": "system", "content": f"[SYSTEM NOTIFICATION: {system_prompt_addition}]"})
    
    async with channel.typing():
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history[channel.id],
                max_tokens=250,
                temperature=0.9
            )
            ai_response = response.choices[0].message.content
            
            ai_response = re.sub(r'\[START_GAME:\s*(.+?)\]', '', ai_response, flags=re.IGNORECASE).strip()
            ai_response = re.sub(r'\[COMMAND:\s*([a-zA-Z_]+)(?:\s+(.+?))?\]', '', ai_response, flags=re.IGNORECASE).strip()
            
            conversation_history[channel.id].append({"role": "assistant", "content": ai_response})
            if len(conversation_history[channel.id]) > MAX_HISTORY + 1:
                conversation_history[channel.id].pop(1)
            name = active_conversations.get(channel.id, f"woolgirl chat {datetime.date.today().strftime('%Y-%m-%d')}")
            save_conversation(channel.id, name)
            
            await channel.send(ai_response)
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
        if channel_id in conversation_history:
            del conversation_history[channel_id]
        if channel_id in active_conversations:
            del active_conversations[channel_id]
            
        if isinstance(channel, discord.DMChannel):
            await channel.send("I erased my internal memory! But since we are in a private DM, Discord physically won't let me delete your messages for you. You'll have to clear the screen yourself, idiot!")
        else:
            await channel.purge(limit=100)
            await channel.send("I erased my memory and deleted the recent chat history. Happy now?!", delete_after=10)

@bot.event
async def on_ready():
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
        
        if channel_id not in conversation_history:
            conversation_history[channel_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

        conversation_history[channel_id].append({"role": "user", "content": f"{message.author.display_name}: {user_msg}"})
        
        if len(conversation_history[channel_id]) > MAX_HISTORY + 1:
            conversation_history[channel_id].pop(1)

        async with message.channel.typing():
            try:
                response = await ai_client.chat.completions.create(
                    model="llama-3.1-8b-instant", 
                    messages=conversation_history[channel_id],
                )
                
                ai_response = response.choices[0].message.content
                print(f"AI RAW RESPONSE: {ai_response}")
                
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

                cmd_match = re.search(r'\[COMMAND:\s*([a-zA-Z_]+)(?:\s+(.+?))?\]', ai_response, re.IGNORECASE)
                sys_command = None
                sys_args = None
                
                if cmd_match:
                    sys_command = cmd_match.group(1).strip().lower()
                    sys_args = cmd_match.group(2).strip() if cmd_match.group(2) else None
                    ai_response = re.sub(r'\[COMMAND:\s*([a-zA-Z_]+)(?:\s+(.+?))?\]', '', ai_response, flags=re.IGNORECASE).strip()
                
                print(f"PARSED CMD: {sys_command}, ARGS: {sys_args}")

                if is_dm and not has_active_save and not sys_command:
                    await message.reply("Hmph! We don't have an active save file right now! You need to use `/new` to create a new conversation, or `/all_conversations` to load an old one before we can talk.")
                    conversation_history[channel_id].pop()
                    return

                # Add AI's raw response to history (so it remembers its tags)
                conversation_history[channel_id].append({"role": "assistant", "content": response.choices[0].message.content})
                
                # Send the response back to Discord
                if file_to_send:
                    await message.reply(ai_response, file=file_to_send)
                else:
                    await message.reply(ai_response)
                    
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
                await message.reply(random.choice(excuses))
                
        # Auto-save after responding
        if is_dm:
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
    if channel_id in conversation_history:
        del conversation_history[channel_id]
    if channel_id in active_conversations:
        del active_conversations[channel_id]
        
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
