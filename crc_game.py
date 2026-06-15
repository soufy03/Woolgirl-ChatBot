import discord
from PIL import Image, ImageDraw, ImageFont
import io
import os
import random

class Card:
    def __init__(self, value, symbol):
        self.value = value
        self.symbol = symbol

def generate_card():
    symbols = ['REVOLVER', 'HEART', 'RETRY', 'NONE']
    weights = [0.3, 0.2, 0.2, 0.3]
    symbol = random.choices(symbols, weights=weights)[0]
    
    if symbol == 'REVOLVER': value = random.randint(3, 10)
    elif symbol == 'HEART': value = random.randint(1, 6)
    elif symbol == 'RETRY': value = random.randint(2, 8)
    else: value = random.randint(1, 10)
        
    return Card(value, symbol)

def generate_crc_board(player_hp, opp_hp, player_cards, opp_cards, opp_hidden=False, player_name="YOU"):
    bg_path = "assets_exact/retouched-image-18.png"
    if os.path.exists(bg_path):
        base = Image.open(bg_path).convert("RGBA").resize((1280, 720))
        overlay = Image.new("RGBA", (1280, 720), (0, 0, 0, 160))
        base = Image.alpha_composite(base, overlay)
    else:
        base = Image.new("RGBA", (1280, 720), (40, 25, 15))
        
    draw = ImageDraw.Draw(base)
    
    try:
        font_small = ImageFont.truetype("assets_exact/PressStart2P-Regular.ttf", 20)
        font_large = ImageFont.truetype("assets_exact/PressStart2P-Regular.ttf", 60)
    except:
        font_small = ImageFont.load_default()
        font_large = ImageFont.load_default()

    icons = {}
    for s in ["HEART", "REVOLVER", "RETRY", "NONE"]:
        try:
            img = Image.open(f"assets_exact/{s}.png").convert("RGBA")
            icons[s] = img.resize((50, 50))
        except:
            pass
            
    heart_icon = icons.get("HEART", None)
    if heart_icon:
        heart_icon = heart_icon.resize((30, 30))
        
    # Opponent HP (Top Left)
    draw.text((30, 30), "WOOLGIRL", fill="#D4AF37", font=font_small)
    if heart_icon:
        for i in range(opp_hp):
            base.paste(heart_icon, (30 + i*40, 70), heart_icon)
            
    # Player HP (Bottom Left)
    draw.text((30, 620), str(player_name).upper(), fill="#D4AF37", font=font_small)
    if heart_icon:
        for i in range(player_hp):
            base.paste(heart_icon, (30 + i*40, 660), heart_icon)

    card_back_path = "assets_exact/retouched-image-19.png"
    card_back_img = None
    if os.path.exists(card_back_path):
        card_back_img = Image.open(card_back_path).convert("RGBA")
        
    def draw_card(x, y, card, hidden=False):
        w, h = 180, 260
        if hidden:
            if card_back_img:
                cb = card_back_img.resize((w, h))
                base.paste(cb, (x, y), cb)
            else:
                draw.rectangle([x, y, x+w, y+h], fill="#351a0e", outline="#D4AF37", width=4)
            return
            
        draw.rectangle([x, y, x+w, y+h], fill="white", outline="#D4AF37", width=4)
        
        if card.symbol in icons:
            ic = icons[card.symbol]
            base.paste(ic, (x+10, y+10), ic)
            base.paste(ic, (x+w-60, y+h-60), ic)
            
        val_str = str(card.value)
        tw = draw.textlength(val_str, font=font_large) if hasattr(draw, 'textlength') else 60
        draw.text((x + w//2 - tw//2, y + 100), val_str, fill="black", font=font_large)

    start_x = 1280//2 - (180*3 + 40*2)//2
    for i, c in enumerate(opp_cards):
        draw_card(start_x + i*220, 80, c, hidden=opp_hidden)
        
    for i, c in enumerate(player_cards):
        draw_card(start_x + i*220, 380, c, hidden=False)
        
    img_byte_arr = io.BytesIO()
    base.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return img_byte_arr

class CRCView(discord.ui.View):
    def __init__(self, player, inject_memory_callback, player_name="YOU", max_hp=3, trigger_ai_callback=None):
        super().__init__(timeout=300)
        self.player = player
        self.inject_memory_callback = inject_memory_callback
        self.trigger_ai_callback = trigger_ai_callback
        self.player_name = str(player_name)
        self.max_hp = max_hp
        self.player_hp = max_hp
        self.opp_hp = max_hp
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

    async def send_embed(self, interaction, log_text, opp_hidden=False):
        img_bytes = generate_crc_board(self.player_hp, self.opp_hp, self.player_cards, self.opp_cards, opp_hidden=opp_hidden, player_name=self.player_name)
        file = discord.File(img_bytes, filename="board.png")
        embed = discord.Embed(title="Crazy Revolver Cards", description=f"```yaml\n> {log_text}\n```", color=0xD4AF37)
        embed.set_image(url="attachment://board.png")
        
        await interaction.edit_original_response(content="", embed=embed, attachments=[file], view=self)

    async def redraw_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not self.check_auth(interaction):
            await interaction.followup.send("Not your game!", ephemeral=True)
            return
            
        self.player_cards = [generate_card() for _ in range(3)]
        self.setup_buttons(phase="deal")
        
        await self.send_embed(interaction, f"You used your Retry! Here is your new hand. Ready to battle?", opp_hidden=True)

    async def reveal_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not self.check_auth(interaction):
            await interaction.followup.send("Not your game!", ephemeral=True)
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

        self.player_hp = min(self.max_hp + 3, self.player_hp + p_heal)
        self.opp_hp = min(self.max_hp + 3, self.opp_hp + o_heal)
        
        self.player_hp -= o_dmg
        self.opp_hp -= p_dmg
        
        battle_log = f"{self.player_name.upper()} TOTAL: {p_total} | WOOLGIRL TOTAL: {o_total}\n"
        if p_total > o_total:
            self.player_hp -= 1
            battle_log += f"💥 Your score was higher! You take 1 damage!\n"
        elif o_total > p_total:
            self.opp_hp -= 1
            battle_log += f"💥 Her score was higher! She takes 1 damage!\n"
        else:
            battle_log += "🛡️ It's a tie! Nobody takes score damage.\n"

        if p_dmg > 0: battle_log += f"🔫 You landed a Revolver combo! She takes {p_dmg} damage!\n"
        if o_dmg > 0: battle_log += f"🔫 She landed a Revolver combo! You take {o_dmg} damage!\n"
        if p_heal > 0: battle_log += f"❤️ You healed {p_heal} HP!\n"
        if o_heal > 0: battle_log += f"❤️ She healed {o_heal} HP!\n"
            
        game_over = False
        ai_msg = ""
        if self.player_hp <= 0 and self.opp_hp <= 0:
            battle_log += "\n💀 IT'S A DOUBLE KO DRAW!"
            game_over = True
            ai_msg = f"The game of Crazy Revolver Cards against {self.player_name} ended in a DRAW! You both died! React to this tie!"
        elif self.player_hp <= 0:
            battle_log += "\n💀 YOU DIED! WOOLGIRL WINS!"
            game_over = True
            ai_msg = f"You just beat {self.player_name} at a game of Crazy Revolver Cards! Gloat about how easily you crushed them!"
        elif self.opp_hp <= 0:
            battle_log += "\n💀 WOOLGIRL DIES! YOU WIN!"
            game_over = True
            ai_msg = f"The user {self.player_name} just beat you at Crazy Revolver Cards! Be very upset, make excuses, and accuse them of cheating!"

        if game_over:
            self.clear_items()
            if self.trigger_ai_callback:
                import asyncio
                asyncio.create_task(self.trigger_ai_callback(interaction.channel, ai_msg))
        else:
            self.setup_buttons(phase="next_round")

        await self.send_embed(interaction, battle_log.strip(), opp_hidden=False)

    async def next_round_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not self.check_auth(interaction):
            await interaction.followup.send("Not your game!", ephemeral=True)
            return
            
        self.start_round()
        await self.send_embed(interaction, "Round starts! Choose your action.", opp_hidden=True)
