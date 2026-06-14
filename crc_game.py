import discord
from PIL import Image, ImageDraw, ImageFont
from pilmoji import Pilmoji
import io
import os
import random

class Card:
    def __init__(self, value, symbol):
        self.value = value
        self.symbol = symbol

def generate_card():
    symbols = ['REVOLVER', 'HEART', 'RETRY', 'NULL']
    weights = [0.3, 0.2, 0.2, 0.3]
    symbol = random.choices(symbols, weights=weights)[0]
    
    if symbol == 'REVOLVER': value = random.randint(3, 10)
    elif symbol == 'HEART': value = random.randint(1, 6)
    elif symbol == 'RETRY': value = random.randint(2, 8)
    else: value = random.randint(1, 10)
        
    return Card(value, symbol)

def generate_crc_board(player_hp, opp_hp, player_cards, opp_cards, opp_hidden=False):
    bg_path = r"C:\Users\benze\Desktop\Dev\CRC\Game_Assets\retouched-image-18.png"
    if os.path.exists(bg_path):
        base = Image.open(bg_path).convert("RGBA").resize((1280, 720))
    else:
        base = Image.new("RGBA", (1280, 720), (30, 20, 10))
        
    try:
        font_large = ImageFont.truetype("arialbd.ttf", 60)
        font_small = ImageFont.truetype("arialbd.ttf", 40)
        font_emoji = ImageFont.truetype("seguiemj.ttf", 45)
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_emoji = ImageFont.load_default()

    draw = ImageDraw.Draw(base)
    
    # Shadow text for HP
    draw.text((52, 52), f"Woolgirl HP: {'❤' * opp_hp}", fill="black", font=font_small)
    draw.text((50, 50), f"Woolgirl HP: {'❤' * opp_hp}", fill="white", font=font_small)
    draw.text((52, 632), f"Your HP: {'❤' * player_hp}", fill="black", font=font_small)
    draw.text((50, 630), f"Your HP: {'❤' * player_hp}", fill="white", font=font_small)
    
    def draw_card(x, y, card, hidden=False):
        w, h = 140, 192
        if hidden:
            draw.rounded_rectangle([x, y, x+w, y+h], radius=10, fill=(139, 69, 19), outline=(101, 67, 33), width=6)
            draw.text((x+50, y+60), "?", fill="white", font=font_large)
            return
            
        draw.rounded_rectangle([x, y, x+w, y+h], radius=10, fill="white", outline="gray", width=4)
        
        symbol_text = "🃏"
        if card.symbol == 'REVOLVER': symbol_text = "🔫"
        elif card.symbol == 'HEART': symbol_text = "❤"
        elif card.symbol == 'RETRY': symbol_text = "🔄"
            
        with Pilmoji(base) as pilmoji:
            pilmoji.text((x+10, y+10), symbol_text, fill="black", font=font_emoji)
            pilmoji.text((x+w-65, y+h-65), symbol_text, fill="black", font=font_emoji)
        
        val_str = str(card.value)
        offset_x = 55 if len(val_str) == 1 else 35
        draw.text((x+offset_x, y+60), val_str, fill="black", font=font_large)

    start_x = 1280//2 - (140*3 + 40*2)//2
    for i, c in enumerate(opp_cards):
        draw_card(start_x + i*180, 150, c, hidden=opp_hidden)
        
    for i, c in enumerate(player_cards):
        draw_card(start_x + i*180, 400, c, hidden=False)
        
    img_byte_arr = io.BytesIO()
    base.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return img_byte_arr

class CRCView(discord.ui.View):
    def __init__(self, player, inject_memory_callback):
        super().__init__(timeout=300)
        self.player = player
        self.inject_memory_callback = inject_memory_callback
        self.player_hp = 3
        self.opp_hp = 3
        self.start_round()
        
    def start_round(self):
        self.player_cards = [generate_card() for _ in range(3)]
        self.opp_cards = [generate_card() for _ in range(3)]
        self.setup_buttons(phase="deal")

    def setup_buttons(self, phase="deal"):
        self.clear_items()
        
        if phase == "deal":
            retry_count = sum(1 for c in self.player_cards if c.symbol == 'RETRY')
            if retry_count >= 2:
                btn = discord.ui.Button(style=discord.ButtonStyle.primary, label="Redraw Hand (Used Retry)", emoji="🔄")
                btn.callback = self.redraw_callback
                self.add_item(btn)
                
            btn2 = discord.ui.Button(style=discord.ButtonStyle.success, label="Reveal & Battle", emoji="⚔️")
            btn2.callback = self.reveal_callback
            self.add_item(btn2)
            
        elif phase == "next_round":
            btn = discord.ui.Button(style=discord.ButtonStyle.primary, label="Next Round", emoji="⏭️")
            btn.callback = self.next_round_callback
            self.add_item(btn)

    def check_auth(self, interaction):
        return interaction.user == self.player

    async def redraw_callback(self, interaction: discord.Interaction):
        if not self.check_auth(interaction):
            await interaction.response.send_message("Not your game!", ephemeral=True)
            return
            
        self.player_cards = [generate_card() for _ in range(3)]
        self.setup_buttons(phase="deal")
        
        img_bytes = generate_crc_board(self.player_hp, self.opp_hp, self.player_cards, self.opp_cards, opp_hidden=True)
        file = discord.File(img_bytes, filename="board.png")
        await interaction.response.edit_message(content="You used your Retry! Here is your new hand. Ready to battle?", attachments=[file], view=self)

    async def reveal_callback(self, interaction: discord.Interaction):
        if not self.check_auth(interaction):
            await interaction.response.send_message("Not your game!", ephemeral=True)
            return

        def eval_hand(cards):
            dmg, heal = 0, 0
            symbols = [c.symbol for c in cards]
            rev_c = symbols.count('REVOLVER')
            hrt_c = symbols.count('HEART')
            
            if rev_c == 2: dmg = 1
            elif rev_c == 3: dmg = 2
            
            if hrt_c == 2: heal = 1
            elif hrt_c == 3: heal = 2
            
            total = sum(c.value for c in cards)
            return dmg, heal, total

        p_dmg, p_heal, p_total = eval_hand(self.player_cards)
        o_dmg, o_heal, o_total = eval_hand(self.opp_cards)

        # Apply healing
        self.player_hp = min(5, self.player_hp + p_heal)
        self.opp_hp = min(5, self.opp_hp + o_heal)
        
        # Apply combo damage
        self.player_hp -= o_dmg
        self.opp_hp -= p_dmg
        
        battle_log = f"Your Total: **{p_total}** | Woolgirl Total: **{o_total}**\n"
        if p_total > o_total:
            self.player_hp -= 1
            battle_log += "💥 Your score was higher! You take 1 damage!"
        elif o_total > p_total:
            self.opp_hp -= 1
            battle_log += "💥 Her score was higher! She takes 1 damage!"
        else:
            battle_log += "🛡️ It's a tie! Nobody takes score damage."

        if p_dmg > 0: battle_log += f"\n🔫 You landed a Revolver combo! She takes {p_dmg} damage!"
        if o_dmg > 0: battle_log += f"\n🔫 She landed a Revolver combo! You take {o_dmg} damage!"
        if p_heal > 0: battle_log += f"\n❤️ You healed {p_heal} HP!"
        if o_heal > 0: battle_log += f"\n❤️ She healed {o_heal} HP!"
            
        game_over = False
        if self.player_hp <= 0 and self.opp_hp <= 0:
            battle_log += "\n\n💀 **IT'S A DOUBLE KO DRAW!**"
            game_over = True
        elif self.player_hp <= 0:
            battle_log += "\n\n💀 **YOU DIED! WOOLGIRL WINS!**"
            game_over = True
            self.inject_memory_callback(interaction.channel_id, "You just beat the user at a game of Crazy Revolver Cards! Gloat about how easily you crushed them!")
        elif self.opp_hp <= 0:
            battle_log += "\n\n💀 **WOOLGIRL DIES! YOU WIN!**"
            game_over = True
            self.inject_memory_callback(interaction.channel_id, "The user just beat you at Crazy Revolver Cards! Be very upset, make excuses, and accuse them of cheating!")

        if game_over:
            self.clear_items()
        else:
            self.setup_buttons(phase="next_round")

        img_bytes = generate_crc_board(self.player_hp, self.opp_hp, self.player_cards, self.opp_cards, opp_hidden=False)
        file = discord.File(img_bytes, filename="board.png")
        await interaction.response.edit_message(content=battle_log, attachments=[file], view=self)

    async def next_round_callback(self, interaction: discord.Interaction):
        if not self.check_auth(interaction):
            await interaction.response.send_message("Not your game!", ephemeral=True)
            return
            
        self.start_round()
        img_bytes = generate_crc_board(self.player_hp, self.opp_hp, self.player_cards, self.opp_cards, opp_hidden=True)
        file = discord.File(img_bytes, filename="board.png")
        await interaction.response.edit_message(content="Round starts! Choose your action.", attachments=[file], view=self)
