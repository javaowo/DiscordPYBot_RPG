import discord # type: ignore
import copy
from typing import cast
import random
import asyncio
import io
from PIL import Image, ImageDraw, ImageFont # type: ignore
from pilmoji import Pilmoji # type: ignore
from engine import char_db, SimpleCharacter, process_special_skill, execute_special_skill, DEBUFF_LIST, process_rain_effects

class SafeView(discord.ui.View):
    """自訂的基礎視窗，專門用來吃掉 404 連點報錯"""
    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        if isinstance(error, discord.NotFound) and getattr(error, "code", 0) == 10062:
            return
        
        import traceback
        print(f"⚠️ UI 錯誤發生在按鈕 {item}:")
        traceback.print_exception(type(error), error, error.__traceback__)

# ==========================================
# 🎨 全局狀態效果 Emoji 映射表 (BUFF + DEBUFF)
# ==========================================
EFFECT_EMOJI_MAP = {
    # (BUFF_LIST)
    "增攻":     "⚔️",
    "增防":     "🛡️",
    "免疫":     "🪽",
    "不屈":     "✊",
    "治癒":     "💚",
    "嘲諷":     "💢",
    "降雨":     "🌧️",
    "反傷":     "🪞",
    "連擊":     "⚡",
    "抗寒":     "❄️",
    "無敵":     "🌟",
    "狂暴":     "😡",
    "保護":     "🔰",
    "迴避":     "💨",
    "醒目":     "👁️",

    # (DEBUFF_LIST)
    "中毒":     "🍄",
    "暈眩":     "💫",
    "昏迷":     "💤",
    "沈默":     "🤫",
    "降攻":     "📉",
    "降防":     "🔓",
    "禁療":     "🚫",
    "封印":     "📴",
    "壓制":     "⛓️",
    "魅惑":     "💖",
    "易傷":     "💔",
    "灼傷":     "🔥",
    "冰凍":     "🧊",
    "鎖定":     "🎯" 
}

def generate_battle_image(attackers, defenders, font_path="font.ttf"):
    img = Image.new("RGB", (1600, 1000), color="#2C2F33")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(font_path, 48)
        small_font = ImageFont.truetype(font_path, 32)
        status_font = ImageFont.truetype(font_path, 26)
    except IOError:
        print("⚠️ 找不到 font.ttf！請確保字體檔放在專案目錄中。")
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()
        status_font = ImageFont.load_default()

    with Pilmoji(img) as pilmoji:
        def draw_team(chars, start_x, start_y, is_attacker):
            for i, c in enumerate(chars):
                y = start_y + i * 185  
                
                name_color = "#5865F2" if is_attacker else "#ED4245" 
                if c.hp <= 0: name_color = "#72767D" 
                pilmoji.text((start_x, y), c.full_name, font=font, fill=name_color)

                if c.hp <= 0:
                    pilmoji.text((start_x, y + 55), "💀 陣亡", font=small_font, fill="#72767D")
                    continue

                bar_width = 480  
                bar_height = 32
                bar_y = y + 60
                
                draw.rectangle([start_x, bar_y, start_x + bar_width, bar_y + bar_height], fill="#4F545C")
                hp_ratio = max(0, min(1, c.hp / c.max_hp))
                fill_color = "#43B581" if hp_ratio > 0.5 else ("#FAA61A" if hp_ratio > 0.2 else "#F04747")
                draw.rectangle([start_x, bar_y, start_x + bar_width * hp_ratio, bar_y + bar_height], fill=fill_color)
                pilmoji.text((start_x + 10, bar_y - 5), f"HP: {int(c.hp)} / {int(c.max_hp)}", font=small_font, fill="#FFFFFF")

                cd_text = f"⏳ 小:{c.small_skill.current_cd} 大:{c.ult_skill.current_cd}"
                if getattr(c, "passive", None) and getattr(c.passive, "cd", 0) > 0:
                    cd_text += f" 被:{getattr(c, 'passive_cd', 0)}"
                pilmoji.text((start_x + bar_width + 20, y + 2), cd_text, font=small_font, fill="#B9BBBE")

                if c.shield_hp > 0:
                    shield_ratio = min(1.0, c.shield_hp / c.max_hp)
                    draw.rectangle([start_x, bar_y + bar_height, start_x + bar_width * shield_ratio, bar_y + bar_height + 8], fill="#00B0F4")
                    pilmoji.text((start_x + bar_width + 20, bar_y - 4), f"🛡️ {int(c.shield_hp)}", font=small_font, fill="#00B0F4")

                # 狀態渲染
                eff_strs = []
                eff_stacks = getattr(c, "effect_stacks", {})

                for k, v in c.effects.items():
                    emoji = EFFECT_EMOJI_MAP.get(k, "")
                    display_name = f"{emoji}{k}" if emoji else k
                    
                    stacks = eff_stacks.get(k, 1)
                    stack_str = f"x{stacks}" if stacks > 1 else ""
                    dur_str = "∞" if v > 100 else str(v)
                    
                    eff_strs.append(f"[{display_name}{stack_str}:{dur_str}R]")
                    
                if eff_strs:
                    line1 = " ".join(eff_strs[:5])
                    pilmoji.text((start_x, bar_y + 42), line1, font=status_font, fill="#FEE75C")
                    
                    if len(eff_strs) > 5:
                        line2 = " ".join(eff_strs[5:10])
                        if len(eff_strs) > 10:
                            line2 += " ..."
                        pilmoji.text((start_x, bar_y + 75), line2, font=status_font, fill="#FEE75C")

        draw_team(attackers, 40, 30, is_attacker=True)
        draw_team(defenders, 860, 30, is_attacker=False)

    draw.line([(820, 20), (820, 980)], fill="#72767D", width=4)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()

def generate_stats_image(attackers, defenders, font_path="font.ttf"):
    img = Image.new("RGB", (1600, 1000), color="#2C2F33")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(font_path, 40)
        small_font = ImageFont.truetype(font_path, 28)
        title_font = ImageFont.truetype(font_path, 50)
    except IOError:
        font = small_font = title_font = ImageFont.load_default()

    with Pilmoji(img) as pilmoji:
        pilmoji.text((800, 20), "📊 戰鬥最終數據面板", font=title_font, fill="#FFFFFF", anchor="mt")
        draw.line([(800, 100), (800, 980)], fill="#72767D", width=4)

        def draw_team_stats(chars, start_x, is_attacker):
            team_title = "🔵 攻擊方 結算數據" if is_attacker else "🔴 防守方 結算數據"
            pilmoji.text((start_x, 90), team_title, font=font, fill="#5865F2" if is_attacker else "#ED4245")

            team_total_dmg = sum([c.stats_dmg_dealt for c in chars]) or 1
            team_total_heal = sum([c.stats_healing_done for c in chars]) or 1
            team_total_taken = sum([c.stats_dmg_taken for c in chars]) or 1

            # MVP判斷
            def get_score(c):
                return c.stats_dmg_dealt + (c.stats_healing_done * 1.2) + (c.stats_dmg_taken * 0.8)
            
            mvp_char = max(chars, key=get_score) if chars else None

            for i, c in enumerate(chars):
                y = 135 + i * 172
                
                # ---------------------------------------------------
                # 🏷️ 名字與 MVP 標籤
                # ---------------------------------------------------
                clean_name = c.full_name
                name_prefix = "💀 " if c.hp <= 0 else ""
                name_text = f"{name_prefix}{clean_name}"
                
                if c == mvp_char:
                    name_text += " 👑 MVP"
                    name_color = "#FFD700" 
                else:
                    name_color = "#FFFFFF" if c.hp > 0 else "#72767D"

                pilmoji.text((start_x, y), name_text, font=font, fill=name_color)

                # ---------------------------------------------------
                # 🟩 極簡血條與護盾指示線
                # ---------------------------------------------------
                line_w = 660  
                line_h = 6    
                hp_y = y + 48
                
                draw.rectangle([start_x, hp_y, start_x + line_w, hp_y + line_h], fill="#4F545C")
                hp_ratio = max(0, min(1, c.hp / c.max_hp))
                hp_fill = "#72767D" if c.hp <= 0 else ("#43B581" if hp_ratio > 0.5 else ("#FAA61A" if hp_ratio > 0.2 else "#F04747"))
                draw.rectangle([start_x, hp_y, start_x + line_w * hp_ratio, hp_y + line_h], fill=hp_fill)

                shield_y = hp_y + line_h
                if c.shield_hp > 0:
                    shield_ratio = min(1.0, c.shield_hp / c.max_hp)
                    draw.rectangle([start_x, shield_y, start_x + line_w * shield_ratio, shield_y + line_h], fill="#00B0F4")

                # ---------------------------------------------------
                # 📊 數據佔比長條圖 (拉開間距不再擁擠)
                # ---------------------------------------------------
                bar_max_w = 320 
                bar_h = 18      
                text_x = start_x
                bar_x = start_x + 340 

                # 👉 將三個長條圖的 Y 軸距離完全拉開
                stat1_y = hp_y + 18
                stat2_y = stat1_y + 34
                stat3_y = stat2_y + 34

                # 🟥 輸出
                dmg_pct = c.stats_dmg_dealt / team_total_dmg
                dmg_w = int(dmg_pct * bar_max_w)
                pilmoji.text((text_x, stat1_y), f"⚔️ 輸出: {c.stats_dmg_dealt} ({dmg_pct*100:.1f}%)", font=small_font, fill="#F04747")
                if dmg_w > 0: draw.rectangle([bar_x, stat1_y + 5, bar_x + dmg_w, stat1_y + 5 + bar_h], fill="#F04747")

                # 🟩 治療
                heal_pct = c.stats_healing_done / team_total_heal
                heal_w = int(heal_pct * bar_max_w)
                pilmoji.text((text_x, stat2_y), f"💚 治療: {c.stats_healing_done} ({heal_pct*100:.1f}%)", font=small_font, fill="#43B581")
                if heal_w > 0: draw.rectangle([bar_x, stat2_y + 5, bar_x + heal_w, stat2_y + 5 + bar_h], fill="#43B581")

                # 🟦 承傷
                taken_pct = c.stats_dmg_taken / team_total_taken
                taken_w = int(taken_pct * bar_max_w)
                pilmoji.text((text_x, stat3_y), f"🛡️ 承傷: {c.stats_dmg_taken} ({taken_pct*100:.1f}%)", font=small_font, fill="#00B0F4")
                if taken_w > 0: draw.rectangle([bar_x, stat3_y + 5, bar_x + taken_w, stat3_y + 5 + bar_h], fill="#00B0F4")

        draw_team_stats(attackers, 60, is_attacker=True)
        draw_team_stats(defenders, 840, is_attacker=False)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()

def get_char_select_options():
    options = []
    role_icons = { "坦克": "🛡️", "輔助": "💖", "戰士": "⚔️", "刺客": "🗡️", "法師": "🔮", "控場者": "💫", "繪域師":"🪄"}
    
    # 定義職業排序權重
    ROLE_ORDER = {"坦克": 1, "輔助": 2, "戰士": 3, "刺客": 4, "法師": 5, "控場者": 6, "繪域師": 7}
    
    # 將角色按職業權重排序，再按名稱排序
    sorted_chars = sorted(
        char_db.items(), 
        key=lambda x: (ROLE_ORDER.get(x[1].get('role', '未知'), 99), x[1]['name'])
    )

    for cid, data in sorted_chars:
        role = data.get("role", "未知定位")
        icon = role_icons.get(role, "👤")
        tags = ", ".join(data.get("tags", []))
        
        options.append(discord.SelectOption(
            label=f"[{role}] {data['name']}"[:100], 
            description=(f"特性：{tags}" if tags else "無")[:100], 
            emoji=icon, value=cid
        ))
    return options

class BattleControlView(SafeView):
    def __init__(self, attackers, defenders, initial_embed):
        super().__init__(timeout=None)
        
        self.atk_blueprints = [(c.cid, c.name) for c in attackers]
        self.def_blueprints = [(c.cid, c.name) for c in defenders]
        self.initial_embed_template = copy.deepcopy(initial_embed)
        
        self.attackers = attackers
        self.defenders = defenders
        
        self.history_embeds = [copy.deepcopy(initial_embed)] 
        
        # 👉 紀錄每回合的截圖 Bytes
        img_bytes = generate_battle_image(self.attackers, self.defenders)
        self.history_images = [img_bytes] 
        
        self.current_index = 0
        self.round_count = 1
        self.battle_ended = False
        self.is_animating = False 
        
        self.update_button_states()
        
    async def refresh_display(self, interaction: discord.Interaction):
        embed = self.history_embeds[self.current_index]
        img_bytes = self.history_images[self.current_index]
        
        # 將二進位資料轉回圖片檔案
        file = discord.File(fp=io.BytesIO(img_bytes), filename="battle.png")
        embed.set_image(url="attachment://battle.png")
        
        # 更新訊息並掛載圖片
        await interaction.edit_original_response(embed=embed, attachments=[file], view=self)

    def recreate_chars(self):
        atks = []
        for cid, cname in self.atk_blueprints:
            c = SimpleCharacter(cid, "攻", char_db)
            c.name = cname
            atks.append(c)
        defs = []
        for cid, cname in self.def_blueprints:
            c = SimpleCharacter(cid, "守", char_db)
            c.name = cname
            defs.append(c)
        return atks, defs

    def update_button_states(self):
        btn_start = cast(discord.ui.Button, self.children[0])
        btn_first = cast(discord.ui.Button, self.children[1])
        btn_prev = cast(discord.ui.Button, self.children[2])
        btn_next = cast(discord.ui.Button, self.children[3])
        btn_last = cast(discord.ui.Button, self.children[4])
        btn_retry = cast(discord.ui.Button, self.children[5])

        if len(self.history_embeds) == 1:
            btn_start.disabled = False
            btn_start.style = discord.ButtonStyle.success
            btn_start.label = "戰鬥開始 ⚔️"
            btn_first.disabled = True
            btn_prev.disabled = True
            btn_next.disabled = True
            btn_last.disabled = True
            btn_retry.disabled = True
        else:
            btn_start.disabled = True
            btn_start.style = discord.ButtonStyle.secondary
            btn_start.label = "播放中... 🎬" if self.is_animating else "戰鬥結束"
            btn_first.disabled = (self.current_index == 0)
            btn_prev.disabled = (self.current_index == 0)
            btn_next.disabled = (self.current_index == len(self.history_embeds) - 1)
            btn_last.disabled = (self.current_index == len(self.history_embeds) - 1)
            btn_retry.disabled = False

    @discord.ui.button(label="戰鬥開始 ⚔️", style=discord.ButtonStyle.success, row=0)
    async def btn_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        try: await interaction.response.defer()
        except discord.NotFound: return 
        
        self.run_auto_battle()
        
        self.is_animating = True
        for i in range(1, len(self.history_embeds)):
            if not self.is_animating:
                break
                
            self.current_index = i
            if i == len(self.history_embeds) - 1:
                self.is_animating = False 
                
            self.update_button_states()
            await self.refresh_display(interaction)
            
            if self.is_animating:
                await asyncio.sleep(10)

    @discord.ui.button(label="⏪ 開場", style=discord.ButtonStyle.secondary, row=1)
    async def btn_first(self, interaction: discord.Interaction, button: discord.ui.Button):
        try: await interaction.response.defer()
        except discord.NotFound: return 
        self.is_animating = False 
        self.current_index = 0
        self.update_button_states()
        await self.refresh_display(interaction)

    @discord.ui.button(label="◀️ 上一回合", style=discord.ButtonStyle.secondary, row=1)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        try: await interaction.response.defer()
        except discord.NotFound: return 
        self.is_animating = False 
        self.current_index = max(0, self.current_index - 1)
        self.update_button_states()
        await self.refresh_display(interaction)

    @discord.ui.button(label="下一回合 ▶️", style=discord.ButtonStyle.primary, row=1)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        try: await interaction.response.defer()
        except discord.NotFound: return 
        self.is_animating = False 
        self.current_index = min(len(self.history_embeds) - 1, self.current_index + 1)
        self.update_button_states()
        await self.refresh_display(interaction)

    @discord.ui.button(label="結算 ⏩", style=discord.ButtonStyle.success, row=1)
    async def btn_last(self, interaction: discord.Interaction, button: discord.ui.Button):
        try: await interaction.response.defer()
        except discord.NotFound: return 
        self.is_animating = False 
        self.current_index = len(self.history_embeds) - 1
        self.update_button_states()
        await self.refresh_display(interaction)

    @discord.ui.button(label="再來一次 🔄", style=discord.ButtonStyle.danger, row=2)
    async def btn_retry(self, interaction: discord.Interaction, button: discord.ui.Button):
        try: await interaction.response.defer()
        except discord.NotFound: return 
        
        self.is_animating = False 
        self.attackers, self.defenders = self.recreate_chars()
        
        # 重置面板與產生新開局圖片
        self.history_embeds = [copy.deepcopy(self.initial_embed_template)]
        self.history_embeds[0].clear_fields()
        self.history_images = [generate_battle_image(self.attackers, self.defenders)]
        
        self.current_index = 0
        self.round_count = 1
        self.battle_ended = False
        
        self.update_button_states()
        await self.refresh_display(interaction)

    def run_auto_battle(self):
        while not self.battle_ended:
            if self.round_count > 20: 
                break

            log_lines = [f"**【第 {self.round_count} 回合戰報】**"]
            
            if not hasattr(self, "active_domain"): 
                self.active_domain, self.domain_owner, self.domain_duration = None, None, 0
                
            if self.round_count == 1:
                for c in self.attackers + self.defenders:
                    if getattr(c, "passive", None) and getattr(c.passive, "special_tag", None) == "qiya_passive":
                        self.active_domain, self.domain_owner, self.domain_duration = "耳機世界", c, 999
                        log_lines.append(f" 🎧 **{c.name}** 展開了領域：【領域展開——耳機世界】！")

            owner = getattr(self, "domain_owner", None)
            if owner is not None:
                if owner.hp <= 0:
                    log_lines.append(f" 📴 **{owner.name}** 陣亡，【{self.active_domain}】領域隨之崩潰消失了。")
                    self.active_domain, self.domain_owner, self.domain_duration = None, None, 0
                # 👉 新增：回合開始時偵測領域是否到期
                elif self.domain_duration <= 0:
                    log_lines.append(f" 📴 【{self.active_domain}】領域的維持時間已到，效果解除了。")
                    self.active_domain, self.domain_owner, self.domain_duration = None, None, 0
            
            # 👉 新增：在每回合開頭顯示當前場地！
            if getattr(self, "active_domain", None):
                dur_text = f" (剩餘 {self.domain_duration} 回合)" if self.domain_duration < 99 else ""
                # 這裡留一個 \n 讓場地標題跟後續的戰鬥分開，比較美觀
                log_lines.append(f" 🌌 **當前場地：【{self.active_domain}】**{dur_text}\n")

            alive_atks = [a for a in self.attackers if a.hp > 0]
            alive_defs = [d for d in self.defenders if d.hp > 0]
            for c in alive_atks + alive_defs:
                # 倪妤被動
                if getattr(c, "passive", None) and getattr(c.passive, "special_tag", None) == "niyu_passive":
                    c.is_immune_to_all = (len(alive_atks) == 1 or len(alive_defs) == 1)
                
                # 👉 🌻 棠謹領域：賦予所有人無法附上狀態的 tag
                c.is_domain_immune = (getattr(self, "active_domain", None) == "繚繞的餘溫")
                
                # 👉 🌻 棠謹被動：只要場上有任何領域，小招就變 0 CD
                if getattr(c, "passive", None) and getattr(c.passive, "special_tag", None) == "tangjin_passive":
                    if getattr(self, "active_domain", None) is not None:
                        c.small_skill.current_cd = 0
            
            for team_atks, team_defs in [(self.attackers, self.defenders), (self.defenders, self.attackers)]:
                if not any(d.hp > 0 for d in team_defs): break
                for char in team_atks:
                    if char.hp <= 0: continue
                    
                    char.newly_applied_this_turn.clear()
                    
                    alive_targets = [t for t in team_defs if t.hp > 0]
                    if not alive_targets: break
                    
                    alive_atks = [a for a in self.attackers if a.hp > 0]
                    alive_defs = [d for d in self.defenders if d.hp > 0]
                    for c in alive_atks + alive_defs:
                        # 倪妤被動
                        if getattr(c, "passive", None) and getattr(c.passive, "special_tag", None) == "niyu_passive":
                            c.is_immune_to_all = (len(alive_atks) == 1 or len(alive_defs) == 1)
                        
                        # 👉 🌻 棠謹領域：賦予所有人無法附上狀態的 tag
                        c.is_domain_immune = (getattr(self, "active_domain", None) == "繚繞的餘溫")
                        
                        # 👉 🌻 棠謹被動：只要場上有任何領域，小招就變 0 CD
                        if getattr(c, "passive", None) and getattr(c.passive, "special_tag", None) == "tangjin_passive":
                            if getattr(self, "active_domain", None) is not None:
                                c.small_skill.current_cd = 0

                    status, msg = char.get_action_status()
                    if status == "skip":
                        log_lines.append(f" ⏳ **{char.name}** {msg}")
                        char.tick_turn_effects(log_lines)
                        if log_lines and log_lines[-1] != "":
                            log_lines.append("")
                        continue

                    char.tick_cd()
                    if status == "charm":
                        action = char.normal_skill
                        targets = [char]
                        log_lines.append(f" {msg}")
                    else:
                        action = char.normal_skill if status == "silence" else char.choose_action()
                        if status == "silence":
                            log_lines.append(f" {msg}")

                        taunted_enemies = [t for t in alive_targets if "嘲諷" in t.effects or "鎖定" in t.effects]
                        base_valid = taunted_enemies if taunted_enemies else alive_targets
                        valid_targets = [t for t in base_valid if "迴避" not in t.effects] or base_valid

                        if action.target_type == "self": 
                            targets = [char]
                        elif action.target_type == "team": 
                            targets = [t for t in team_atks if t.hp > 0]
                        elif action.target_type == "all" or getattr(action, "special_tag", None) == "dummy_normal": 
                            targets = alive_targets
                        elif action.target_type == "primary_and_all":
                            primary = random.choice(valid_targets)
                            targets = [primary] + [t for t in alive_targets if t != primary]
                        elif action.target_type == "random_multi":
                            # 1. 先決定技能「想要」打幾個人
                            if getattr(action, "target_count", 0) > 0:
                                desired_targets = action.target_count
                            else:
                                desired_targets = random.randint(2, 3)
                                
                            if taunted_enemies:
                                # 嘲諷目標中也要優先避開有迴避的
                                guaranteed = random.choice([t for t in taunted_enemies if "迴避" not in t.effects] or taunted_enemies)
                                remaining_pool = [t for t in alive_targets if t != guaranteed]
                                evasion_pool = [t for t in remaining_pool if "迴避" not in t.effects] or remaining_pool
                                
                                # 👉 安全取樣：確保抽取的數量不會大於池子的人數
                                others_count = min(desired_targets - 1, len(evasion_pool))
                                others = random.sample(evasion_pool, others_count) if remaining_pool else []
                                targets = [guaranteed] + others
                            else:
                                # 👉 安全取樣：確保不會超過 valid_targets (扣除迴避後) 的總人數
                                actual_count = min(desired_targets, len(valid_targets))
                                targets = random.sample(valid_targets, actual_count)
                        else:
                            if getattr(char, "passive", None) and getattr(char.passive, "special_tag", None) == "zixu_passive":
                                coma_targets = [t for t in valid_targets if "昏迷" in t.effects]
                                if coma_targets:
                                    valid_targets = coma_targets

                            if action.target_type == "lowest_hp":
                                targets = [min(valid_targets, key=lambda x: x.hp)]
                            elif action.target_type == "highest_atk":
                                targets = [max(valid_targets, key=lambda x: x.get_current_atk())]
                            else:
                                targets = [random.choice(valid_targets)]
                                
                    primary_targets = list(targets) if 'targets' in locals() else []
                    
                    has_combo_before_attack = "連擊" in char.effects
                    
                    if char.cid != "dummy":
                        icon = "🛡️" if action.target_type in ["self", "team"] else ("🗡️" if action.category == "normal" else "🔥")
                        log_lines.append(f"{icon} **{char.name}** 釋放【{action.name}】！")
                        if status == "silence": log_lines[-1] += " (受沈默影響，強制普攻)"
                        if action.target_type == "primary_and_all" and targets:
                            log_lines.append(f" 🎯 鎖定了 **{targets[0].name}** 為主要目標！")

                    if getattr(action, "apply_effect_first", False) and action.effect != "none":
                        for t in targets:
                            if t.hp > 0 and random.randint(1, 100) <= getattr(action, "effect_chance", 100):
                                t.add_effect(action.effect, getattr(action, "effect_duration", 2), log_lines, value=getattr(action, "effect_value", 0))
                                
                    if action.special_tag == "zixu_small":
                        char.add_effect("增攻", 2, log_lines)

                    target_data = {} # 紀錄每個人的專屬數據 {target: {'dmg': 0, 'hits': 0, 'logs': []}}
                    is_true = getattr(action, "damage_type", "normal") == "true"

                    # 1. 後台默默打完所有段數與目標
                    for hit in range(1, action.hits + 1):
                        if action.target_type == "random_single_per_hit":
                            alive_targets = [t for t in team_defs if t.hp > 0]
                            if not alive_targets: break
                            current_taunted = [t for t in alive_targets if "嘲諷" in t.effects]
                            targets = [random.choice(current_taunted)] if current_taunted else [random.choice(alive_targets)]
                            
                        actual_hit_targets = [t for t in targets if t.hp > 0]
                        target_count = len(actual_hit_targets)
                        if target_count == 0: continue
                            
                        for t in actual_hit_targets:
                            # 幫這個目標建立專屬的計分板
                            if t not in target_data:
                                target_data[t] = {'dmg': 0, 'hits': 0, 'logs': []}
                                
                            if action.special_tag == "zixu_ult" and hit == 1:
                                from engine import BUFF_LIST 
                                buffs = [k for k in t.effects.keys() if k in BUFF_LIST]
                                if buffs:
                                    dispelled = random.choice(buffs)
                                    del t.effects[dispelled]
                                    if dispelled in getattr(t, "effect_stacks", {}): del t.effect_stacks[dispelled]
                                    target_data[t]['logs'].append(f" 💨 **{char.name}** 的夕陽餘暉驅散了 **{t.name}** 的 [{EFFECT_EMOJI_MAP.get(dispelled, '')}{dispelled}]！")
                                    
                            current_mult = action.multiplier
                            if getattr(action, "is_split_damage", False):
                                current_mult = current_mult / target_count
                            if getattr(action, "special_tag", None):
                                is_primary = (action.target_type == "primary_and_all" and t == targets[0])
                                current_mult, _ = process_special_skill(action.special_tag, char, t, current_mult, 100, actual_hit_targets, is_primary)
                            
                            skill_atk = int(char.get_current_atk() * current_mult)

                            if skill_atk > 0:
                                dmg, passive_logs = t.take_damage(attacker=char, base_damage=skill_atk, is_true_damage=is_true)
                                target_data[t]['dmg'] += dmg 
                                target_data[t]['hits'] += 1  # 👉 獨立計算該目標實際被打中的段數
                                target_data[t]['logs'].extend(passive_logs)
                                
                            if "音樂" in t.effects and target_data[t]['dmg'] > 0 and not is_true:
                                can_trigger = False
                                if char.cid == "qiya": 
                                    can_trigger, t.music_mark_source_atk = True, char.get_current_atk()
                                elif getattr(self, "active_domain", None) == "耳機世界":
                                    domain_team = self.attackers if self.domain_owner in self.attackers else self.defenders
                                    if char in domain_team: can_trigger = True
                                        
                                if can_trigger:
                                    stacks = getattr(t, "effect_stacks", {}).get("音樂", 1)
                                    mark_atk = getattr(t, "music_mark_source_atk", char.get_current_atk()) 
                                    extra_dmg = int(mark_atk * 0.03 * stacks)
                                    if extra_dmg > 0:
                                        edmg, elogs = t.take_damage(attacker=char, base_damage=extra_dmg)
                                        target_data[t]['dmg'] += edmg
                                        target_data[t]['logs'].extend(elogs)
                                
                            if (action.target_type == "random_single_per_hit" or getattr(action, "apply_effect_per_hit", False)) and action.effect != "none":
                                if random.randint(1, 100) <= getattr(action, "effect_chance", 100):
                                    t.add_effect(action.effect, getattr(action, "effect_duration", 2), target_data[t]['logs'], value=getattr(action, "effect_value", 0))

                    # 2. 結算輸出 (獨立排版與智慧防洗頻)
                    total_overall = sum(d['dmg'] for d in target_data.values())
                    dmg_type_str = "真實傷害" if is_true else "傷害"

                    if total_overall > 0 or any(d['logs'] for d in target_data.values()):
                        # 💡 全體攻擊排版
                        if (action.target_type in ["all", "primary_and_all"] or getattr(action, "special_tag", None) == "dummy_normal") and len(target_data) > 1:
                            max_hits = max((d['hits'] for d in target_data.values()), default=1)
                            hit_text = f" (共 {max_hits} 段)" if max_hits > 1 else ""
                            if total_overall > 0:
                                log_lines.append(f" └ 對 **全體目標** 總計造成 `{total_overall}` {dmg_type_str}{hit_text}！")
                            
                            # 全體攻擊的被動，合在一起並利用 dict.fromkeys() 去除一模一樣的重複廢話
                            all_logs = []
                            for d in target_data.values(): all_logs.extend(d['logs'])
                            log_lines.extend(list(dict.fromkeys(all_logs)))
                            
                        # 💡 單體或隨機多體排版 (先顯示擊中 A，再顯示 A 的護盾/無敵，順序完美！)
                        else:
                            for t, data in target_data.items():
                                if data['dmg'] > 0 or data['logs']:
                                    hit_text = f" (共 {data['hits']} 段)" if data['hits'] > 1 else ""
                                    if data['dmg'] > 0:
                                        log_lines.append(f" └ 擊中 **{t.name}**，總計造成 `{data['dmg']}` {dmg_type_str}{hit_text}！")
                                    elif data['logs']:
                                        log_lines.append(f" └ 擊中 **{t.name}**，造成 `0` {dmg_type_str}{hit_text}！")
                                    
                                    # 專屬被動印出，同樣過濾掉重複的洗頻
                                    log_lines.extend(list(dict.fromkeys(data['logs'])))

                    if action.effect != "none" and char.hp > 0 and not getattr(action, "apply_effect_first", False) and action.target_type != "random_single_per_hit" and not getattr(action, "apply_effect_per_hit", False):
                        effect_val = getattr(action, "effect_value", 0)
                        target_list = targets if action.effect in DEBUFF_LIST else [char]
                        if action.target_type == "team": target_list = targets
                        
                        for t in target_list:
                            if t.hp > 0:
                                current_chance = getattr(action, "effect_chance", 100)
                                if getattr(action, "special_tag", None):
                                    is_primary = (action.target_type == "primary_and_all" and t == targets[0])
                                    _, current_chance = process_special_skill(action.special_tag, char, t, 1.0, current_chance, alive_targets, is_primary)
                                    
                                if random.randint(1, 100) <= current_chance:
                                    t.add_effect(action.effect, getattr(action, "effect_duration", 2), log_lines, value=effect_val)

                    if getattr(action, "special_tag", None):
                        if action.special_tag == "tangjin_ult":
                            self.active_domain, self.domain_owner, self.domain_duration = "繚繞的餘溫", char, 3
                            log_lines.append(f" 🌻 **{char.name}** 展開了領域：【領域展開——繚繞的餘溫】！") 
                            for c in alive_atks + alive_defs:
                                c.is_domain_immune = True
                        allies_list = team_defs if char in team_atks else team_atks
                        my_team_list = team_atks if char in team_atks else team_defs
                        execute_special_skill(action.special_tag, char, char, targets, log_lines, allies=allies_list, my_team=my_team_list)

                    if action.category != "normal": action.current_cd = action.cd
                    
                    if has_combo_before_attack and primary_targets:
                        log_lines.append(f" ⏳ **{char.name}** 觸發 [連擊]Buff！複製施放【{action.name}】！")
                        
                        # 🌟 1. 改用獨立結算結構，取代舊的 map 和 list
                        combo_data = {}
                        
                        for hit in range(1, action.hits + 1):
                            actual_hit_targets = [t for t in primary_targets if t.hp > 0]
                            if not actual_hit_targets: break
                            
                            for t in actual_hit_targets:
                                # 幫該目標建立計分板
                                if t not in combo_data:
                                    combo_data[t] = {'dmg': 0, 'hits': 0, 'logs': []}
                                    
                                current_mult = action.multiplier * 0.5
                                if getattr(action, "is_split_damage", False):
                                    current_mult = current_mult / len(actual_hit_targets)
                                    
                                if getattr(action, "special_tag", None):
                                    is_primary = (action.target_type == "primary_and_all" and t == primary_targets[0])
                                    current_mult, _ = process_special_skill(action.special_tag, char, t, current_mult, 100, actual_hit_targets, is_primary)
                                
                                skill_atk = int(char.get_current_atk() * current_mult)
                                if skill_atk > 0:
                                    dmg, passive_logs = t.take_damage(attacker=char, base_damage=skill_atk, is_true_damage=is_true)
                                    combo_data[t]['dmg'] += dmg
                                    combo_data[t]['hits'] += 1       # 👉 獨立計算連擊打中幾段
                                    combo_data[t]['logs'].extend(passive_logs)
                                    
                                if "音樂" in t.effects and combo_data[t]['dmg'] > 0 and not is_true:
                                    can_trigger = False
                                    if char.cid == "qiya": 
                                        can_trigger, t.music_mark_source_atk = True, char.get_current_atk()
                                    elif getattr(self, "active_domain", None) == "耳機世界":
                                        domain_team = self.attackers if self.domain_owner in self.attackers else self.defenders
                                        if char in domain_team: can_trigger = True
                                            
                                    if can_trigger:
                                        stacks = getattr(t, "effect_stacks", {}).get("音樂", 1)
                                        mark_atk = getattr(t, "music_mark_source_atk", char.get_current_atk()) 
                                        extra_dmg = int(mark_atk * 0.03 * stacks)
                                        if extra_dmg > 0:
                                            edmg, elogs = t.take_damage(attacker=char, base_damage=extra_dmg, is_true_damage=True)
                                            combo_data[t]['dmg'] += edmg
                                            combo_data[t]['logs'].append(f" 🎵 [印記共鳴] (連擊)觸發 {stacks} 層 [音樂]印記，追加 `{edmg}` 點真實傷害！")
                                            combo_data[t]['logs'].extend(elogs)

                        # 🌟 2. 結算輸出 (獨立排版與智慧防洗頻)
                        combo_total = sum(d['dmg'] for d in combo_data.values())
                        
                        if combo_total > 0 or any(d['logs'] for d in combo_data.values()):
                            if (action.target_type in ["all", "primary_and_all"] or getattr(action, "special_tag", None) == "dummy_normal") and len(combo_data) > 1:
                                max_hits = max((d['hits'] for d in combo_data.values()), default=1)
                                hit_text = f" (共 {max_hits} 段)" if max_hits > 1 else ""
                                
                                if combo_total > 0:
                                    log_lines.append(f" └ (連擊)對 **全體目標** 總計造成 `{combo_total}` {dmg_type_str}{hit_text}！")
                                
                                # 合併全體連擊被動並去重複
                                all_logs = []
                                for d in combo_data.values(): all_logs.extend(d['logs'])
                                log_lines.extend(list(dict.fromkeys(all_logs)))
                            else:
                                for t, data in combo_data.items():
                                    if data['dmg'] > 0 or data['logs']:
                                        hit_text = f" (共 {data['hits']} 段)" if data['hits'] > 1 else ""
                                        if data['dmg'] > 0:
                                            log_lines.append(f" └ (連擊)擊中 **{t.name}**，總計造成 `{data['dmg']}` {dmg_type_str}{hit_text}！")
                                        elif data['logs']:
                                            log_lines.append(f" └ (連擊)擊中 **{t.name}**，造成 `0` {dmg_type_str}{hit_text}！")
                                        
                                        # 單體連擊被動印出並去重複
                                        log_lines.extend(list(dict.fromkeys(data['logs'])))

                    if char.hp > 0 and getattr(char, "passive", None) and getattr(char.passive, "special_tag", None) == "xinqiao_passive":
                        if getattr(char, "passive_cd", 0) <= 0:
                            if primary_targets:
                                passive_target = primary_targets[0]
                                log_lines.append(f" 🌸 **{char.name}** 觸發被動 [花香撲鼻]！")
                                
                                if passive_target.hp > 0:
                                    char.passive_cd = getattr(char.passive, "cd", 1)
                                    normal_skill = char.normal_skill
                                    pdmg, p_logs = passive_target.take_damage(attacker=char, base_damage=int(char.get_current_atk() * normal_skill.multiplier))
                                    log_lines.append(f" └ 追加普攻擊中 **{passive_target.name}**，造成 `{pdmg}` 傷害！")
                                    log_lines.extend(p_logs)
                                    
                                    # 結算普攻附帶的 15% 昏迷
                                    if getattr(normal_skill, "effect", "none") != "none":
                                        if random.randint(1, 100) <= getattr(normal_skill, "effect_chance", 100):
                                            passive_target.add_effect(normal_skill.effect, getattr(normal_skill, "effect_duration", 1), log_lines)
                                else:
                                    log_lines.append(f" └ 馨喬試圖追加普攻，但原目標 **{passive_target.name}** 已經陣亡，追加落空！")

                    if char.hp > 0 and char.passive and char.passive.trigger == "on_turn_end":
                        if getattr(char, "passive_cd", 0) <= 0:
                            if char.passive.special_tag == "youda_passive":
                                alive_enemies = [t for t in team_defs if t.hp > 0] if char in team_atks else [t for t in team_atks if t.hp > 0]
                                if alive_enemies:
                                    poisoned = [t for t in alive_enemies if "中毒" in t.effects]
                                    target = random.choice(poisoned) if poisoned else random.choice(alive_enemies)
                                    
                                    pdmg, p_logs = target.take_damage(attacker=char, base_damage=int(char.get_current_atk() * 1))
                                    log_lines.append(f" 🧪 **{char.name}** 回合結束觸發被動！對 **{target.name}** 噴灑酸液，造成 `{pdmg}` 傷害！")
                                    log_lines.extend(p_logs)
                                    
                                    if random.randint(1, 100) <= 75 and "中毒" in target.effects:
                                        target.effects["中毒"] += 1
                                        log_lines.append(f" ☠️ **{target.name}** 身上的 [中毒] 擴散了，延長 1 回合！")
                                    char.passive_cd = char.passive.cd
                        else:
                            char.passive_cd -= 1
                            
                    char.tick_turn_effects(log_lines)
                    if log_lines and log_lines[-1] != "":
                        log_lines.append("")

            for c in self.attackers + self.defenders:
                if c.hp > 0: c.tick_round_effects(log_lines)
                
            process_rain_effects(self.attackers, self.defenders, log_lines)
            process_rain_effects(self.defenders, self.attackers, log_lines)
            
            if getattr(self, "active_domain", None):
                self.domain_duration -= 1
            self.round_count += 1
            atk_alive = any(a.hp > 0 for a in self.attackers)
            def_alive = any(d.hp > 0 for d in self.defenders)
            if not atk_alive or not def_alive or self.round_count > 20: self.battle_ended = True

            # ✂️ --- 字數防爆與自動分頁處理 ---
            chunks = []
            curr_chunk = []
            curr_len = 0
            
            for line in log_lines:
                length = len(line) + 1
                if curr_len + length > 3800:
                    chunks.append(curr_chunk)
                    curr_chunk = [line]
                    curr_len = length
                else:
                    curr_chunk.append(line)
                    curr_len += length
            if curr_chunk:
                chunks.append(curr_chunk)

            for idx, chunk in enumerate(chunks):
                new_embed = copy.deepcopy(self.history_embeds[-1])
                new_embed.clear_fields()
                
                img_bytes = generate_battle_image(self.attackers, self.defenders)
                self.history_images.append(img_bytes)
                
                desc_text = "\n".join(chunk)
                if len(chunks) > 1:
                    desc_text = f"*(🔥 本回合戰報分頁：第 {idx+1}/{len(chunks)} 頁)*\n\n" + desc_text
                
                new_embed.description = desc_text
                self.history_embeds.append(new_embed)

            # 🏁 --- 處理戰鬥結算面板 ---
            if self.battle_ended:
                end_text = ""
                atk_alive_count = sum(1 for a in self.attackers if a.hp > 0)
                def_alive_count = sum(1 for d in self.defenders if d.hp > 0)

                if self.round_count > 20 and atk_alive_count > 0 and def_alive_count > 0:
                    # 20 回合血線裁決
                    atk_hp_ratio = sum(a.hp for a in self.attackers) / sum(a.max_hp for a in self.attackers)
                    def_hp_ratio = sum(d.hp for d in self.defenders) / sum(d.max_hp for d in self.defenders)
                    
                    atk_pct = f"{atk_hp_ratio * 100:.1f}%"
                    def_pct = f"{def_hp_ratio * 100:.1f}%"
                    
                    end_text = f"⏱️ **20 回合已達上限，進入血線裁決！**\n🔵 攻擊方剩餘血線：`{atk_pct}`\n🔴 防守方剩餘血線：`{def_pct}`\n\n"
                    
                    if atk_hp_ratio > def_hp_ratio:
                        end_text += "🎉 **攻擊方以血線優勢獲得最終勝利！**"
                        final_color = discord.Color.green()
                    elif def_hp_ratio > atk_hp_ratio:
                        end_text += "🎉 **防守方以血線優勢獲得最終勝利！**"
                        final_color = discord.Color.red()
                    else:
                        end_text += "🤝 **雙方血線完全一致，本局平手！**"
                        final_color = discord.Color.orange()
                else:
                    # 正常擊殺勝利
                    atk_alive = atk_alive_count > 0
                    end_text = f"🎉 **{'攻擊方' if atk_alive else '防守方'}獲得最終勝利！**"
                    final_color = discord.Color.green() if atk_alive else discord.Color.red()

                # 👉 清爽的 Embed 內文 (文字長條圖被移除了，因為我們有更高級的圖片！)
                stats_text = end_text
                
                last_embed = self.history_embeds[-1]
                last_embed.title = "🏁 5v5 世紀大亂鬥 結束 🏁"
                last_embed.color = final_color

                if len(last_embed.description) + len(stats_text) > 3800:
                    stats_embed = copy.deepcopy(last_embed)
                    stats_embed.description = stats_text
                    self.history_embeds.append(stats_embed)
                    # 👉 核心魔法：這裡不再複製最後一幀戰鬥圖，而是呼叫我們剛寫好的圖表生成器！
                    self.history_images.append(generate_stats_image(self.attackers, self.defenders))
                else:
                    last_embed.description += "\n\n" + stats_text
                    # 👉 如果沒有分頁，我們就直接把最後一頁的圖片換成圖表！
                    self.history_images[-1] = generate_stats_image(self.attackers, self.defenders)

# ==========================================
# 🌟 1. 取得分類好的角色選項
# ==========================================
def get_categorized_options():
    categories = {
        "🛡️ 一般攻擊區": ["戰士", "刺客", "法師"],
        "🔮 團隊輔助區": ["坦克", "輔助"],
        "💖 特殊職業區": ["繪域師", "控場者"]
    }
    
    # 1. 定義職業排序權重
    ROLE_ORDER = {"坦克": 1, "輔助": 2, "戰士": 3, "刺客": 4, "法師": 5, "控場者": 6, "繪域師": 7}
    
    # 2. 將角色按「職業權重」排序，再按名稱排序
    sorted_chars = sorted(
        char_db.items(), 
        key=lambda x: (ROLE_ORDER.get(x[1].get('role', '未知'), 99), x[1]['name'])
    )
    
    cat_options = {"🛡️ 一般攻擊區": [], "🔮 團隊輔助區": [], "💖 特殊職業區": []}
    role_icons = { "坦克": "🛡️", "法師": "🔮", "戰士": "⚔️", "刺客": "🗡️", "輔助": "💖", "控場者": "💫", "繪域師":"🪄"}
    
    for cid, data in sorted_chars:
        if cid == "dummy": continue
        role = data.get("role", "未知定位")
        icon = role_icons.get(role, "👤")
        tags = ", ".join(data.get("tags", []))
        desc = (f"特性：{tags}" if tags else "無")[:100]
        
        opt = discord.SelectOption(label=f"[{role}] {data['name']}"[:100], description=desc, emoji=icon, value=cid)
        
        # 尋找對應分類並加入
        for cat_name, roles in categories.items():
            if role in roles:
                cat_options[cat_name].append(opt)
                break
                
    return cat_options

# ==========================================
# 🌟 2. 建立專屬的分類下拉選單
# ==========================================
class CategorySelect(discord.ui.Select):
    def __init__(self, placeholder, options, max_sel, parent_view):
        actual_max = min(max_sel, len(options))
        
        super().__init__(placeholder=placeholder, min_values=1, max_values=actual_max, options=options)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # 將玩家選擇的角色加入隊伍 (最多 5 人且不重複)
        for val in self.values:
            if val not in self.parent_view.team and len(self.parent_view.team) < 5:
                self.parent_view.team.append(val)
                
        await self.parent_view.refresh_ui(interaction)

# ==========================================
# 🎮 單機版防呆與導航系統 (SetupView & TeamOrderView)
# ==========================================
class SetupView(SafeView):
    def __init__(self, step="select_atk", atk_ids=None):
        super().__init__(timeout=300)
        self.step = step
        self.atk_ids = atk_ids or []
        self.team = []
        
        self.build_ui()

    def build_ui(self):
        self.clear_items()
        cat_options = get_categorized_options()
        
        if len(self.team) < 5:
            for cat_name, options in cat_options.items():
                if options:
                    max_sel = min(5, 5 - len(self.team))
                    sel = CategorySelect(f"從 {cat_name} 挑選...", options[:25], max_sel, self)
                    self.add_item(sel)
        
        confirm_btn = discord.ui.Button(label="✅ 確定陣容", style=discord.ButtonStyle.success, disabled=(len(self.team) != 5), row=4)
        confirm_btn.callback = self.on_confirm
        self.add_item(confirm_btn)
        
        clear_btn = discord.ui.Button(label="🗑️ 清空重選", style=discord.ButtonStyle.secondary, disabled=(len(self.team) == 0), row=4)
        clear_btn.callback = self.on_clear
        self.add_item(clear_btn)
        
        cancel_btn = discord.ui.Button(label="❌ 取消設定", style=discord.ButtonStyle.danger, row=4)
        cancel_btn.callback = self.on_cancel
        self.add_item(cancel_btn)

    def get_embed(self):
        side = "⚔️ 攻擊方" if self.step == "select_atk" else "🛡️ 防守方"
        embed = discord.Embed(title=f"{side} - 陣容組建中 ({len(self.team)}/5)", color=discord.Color.blue())
        
        if not self.team:
            embed.description = "請從下方選單挑選角色加入隊伍...\n*(💡 提示：出手順序將完全依照你挑選的先後順序決定！)*"
        else:
            names = [char_db[cid]["name"] for cid in self.team]
            embed.description = "**目前陣容 (依出手順序)：**\n" + "\n".join([f"{i+1}. {name.split('．')[-1]}" for i, name in enumerate(names)])
            if len(self.team) == 5:
                embed.description += "\n\n✨ **陣容已滿！請點擊 [確定陣容]**"
                
        return embed

    async def refresh_ui(self, interaction):
        self.build_ui()
        await interaction.edit_original_response(embed=self.get_embed(), view=self)

    async def on_clear(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.team = []
        await self.refresh_ui(interaction)

    async def on_cancel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.edit_original_response(content="🚫 已取消 5v5 戰鬥設定。", view=None, embed=None)

    async def on_confirm(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.step == "select_atk":
            self.atk_ids = self.team.copy()
            next_view = SetupView(step="select_def", atk_ids=self.atk_ids)
            await interaction.edit_original_response(embed=next_view.get_embed(), view=next_view)
        else:
            def_ids = self.team.copy()
            await interaction.edit_original_response(content="✅ 雙方陣容確認完畢，戰鬥準備開始！", embed=None, view=None)
            
            # 👉 直接進入戰鬥，不再呼叫 start_order_phase
            from ui import BattleControlView
            from engine import SimpleCharacter
            atks = [SimpleCharacter(cid, "攻", char_db) for cid in self.atk_ids]
            defs = [SimpleCharacter(cid, "守", char_db) for cid in def_ids]
            
            embed = discord.Embed(title="⚔️ 5v5 世紀大亂鬥 啟動 ⚔️", description="雙方已就緒，請點擊下方 [戰鬥開始] 進行模擬！", color=discord.Color.gold())
            view = BattleControlView(atks, defs, embed)
            await view.refresh_display(interaction)


class TeamOrderView(SafeView):
    def __init__(self, team_name, team_chars, back_cb, cancel_cb, next_cb):
        super().__init__(timeout=180)
        self.team_name = team_name
        self.team_chars = team_chars
        self.back_cb = back_cb
        self.cancel_cb = cancel_cb
        self.next_cb = next_cb
        self.selected_order = []
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        
        for i, char in enumerate(self.team_chars):
            is_selected = char in self.selected_order
            c_name = char.name.split('(')[1].replace(')','') if "(" in char.name else char.name
            label = f"{self.selected_order.index(char) + 1}. {c_name} ({char.role})" if is_selected else f"{c_name} ({char.role})"
            style = discord.ButtonStyle.primary if is_selected else discord.ButtonStyle.secondary
            
            def make_callback(c):
                async def cb(interaction):
                    await interaction.response.defer() # 👉 每個按鈕都加上 defer
                    self.selected_order.append(c)
                    self.update_buttons()
                    await self.refresh_ui(interaction)
                return cb

            btn = discord.ui.Button(label=label, style=style, disabled=is_selected, custom_id=f"order_{i}", row=0 if i<3 else 1)
            btn.callback = make_callback(char)
            self.add_item(btn)

        reset_btn = discord.ui.Button(label="🔄 重設順序", style=discord.ButtonStyle.primary, row=2)
        async def reset_cb(interaction):
            await interaction.response.defer()
            self.selected_order.clear()
            self.update_buttons()
            await self.refresh_ui(interaction)
        reset_btn.callback = reset_cb
        self.add_item(reset_btn)

        if len(self.selected_order) == len(self.team_chars):
            confirm_btn = discord.ui.Button(label="✅ 確認出戰", style=discord.ButtonStyle.success, row=2)
            async def confirm_cb(interaction):
                await interaction.response.defer()
                await self.next_cb(interaction, self.selected_order)
            confirm_btn.callback = confirm_cb
            self.add_item(confirm_btn)

        back_btn = discord.ui.Button(label="◀️ 上一頁 (重選角色)", style=discord.ButtonStyle.secondary, row=3)
        async def back_cb(interaction): 
            await interaction.response.defer()
            await self.back_cb(interaction)
        back_btn.callback = back_cb
        self.add_item(back_btn)

        cancel_btn = discord.ui.Button(label="❌ 取消對戰設定", style=discord.ButtonStyle.danger, row=3)
        async def cancel_cb(interaction): 
            await interaction.response.defer()
            await self.cancel_cb(interaction)
        cancel_btn.callback = cancel_cb
        self.add_item(cancel_btn)

    async def refresh_ui(self, interaction: discord.Interaction):
        desc = "請依序點擊角色，決定他們在戰鬥中的出手順序：\n\n**👥 你的陣容預覽：**\n"
        for c in self.team_chars:
            tags = ", ".join(c.tags) if c.tags else "無"
            c_name = c.name.split('(')[1].replace(')','') if "(" in c.name else c.name
            desc += f"🔸 **{c_name}** ({c.role}) | 特性: `{tags}`\n"
        
        desc += "\n**⚔️ 目前出戰順序：**\n"
        desc += " ➔ ".join([f"{c.name.split('(')[1].replace(')','')}({c.role})" for c in self.selected_order]) if self.selected_order else "尚未選擇..."
        
        embed = discord.Embed(title=f"⚙️ 陣容配置：決定【{self.team_name}】順序", description=desc, color=discord.Color.blue())
        # 👉 因為前面已經全面 defer()，這邊一律用 edit_original_response 即可
        await interaction.edit_original_response(content="", embed=embed, view=self)


# ==========================================
# 🚀 單機版遊戲啟動流程
# ==========================================
async def start_order_phase(interaction, atk_ids, def_ids):
    atk_chars = [SimpleCharacter(pid, f"攻", char_db) for pid in atk_ids]
    def_chars = [SimpleCharacter(did, f"守", char_db) for did in def_ids]

    async def cancel_setup(inter):
        await inter.edit_original_response(content="🚫 已取消 5v5 戰鬥設定。", view=None, embed=None)

    async def show_atk_order(inter):
        async def back_to_def_select(i):
            view = SetupView(step="select_def", atk_ids=atk_ids)
            await i.edit_original_response(content="⚔️ 攻擊方已就緒！請選擇**防守方**陣容：", view=view, embed=None)
            
        view = TeamOrderView("🔵 攻擊方隊伍", atk_chars, back_cb=back_to_def_select, cancel_cb=cancel_setup, next_cb=show_def_order)
        await view.refresh_ui(inter)

    async def show_def_order(inter, atk_ordered):
        async def back_to_atk_order(i):
            await show_atk_order(i)
            
        async def start_actual_battle(i, def_ordered):
                
            for idx, c in enumerate(atk_ordered): c.name = f"攻{idx+1}({c.name.split('(')[1].replace(')','')})"
            for idx, c in enumerate(def_ordered): c.name = f"守{idx+1}({c.name.split('(')[1].replace(')','')})"

            initial_embed = discord.Embed(title="⚔️ 5v5 世紀大亂鬥 ⚔️", description="雙方佈陣皆已就緒！點擊下方按鈕產生第一回合戰報。", color=discord.Color.gold())
            view = BattleControlView(atk_ordered, def_ordered, initial_embed)
            file = discord.File(fp=io.BytesIO(view.history_images[0]), filename="battle.png")
            initial_embed.set_image(url="attachment://battle.png")
            
            # 記得加入 attachments=[file]
            await i.edit_original_response(content="", embed=initial_embed, attachments=[file], view=view)

        view = TeamOrderView("🔴 防守方隊伍", def_chars, back_cb=back_to_atk_order, cancel_cb=cancel_setup, next_cb=start_actual_battle)
        await view.refresh_ui(inter)

    await show_atk_order(interaction)


# ==========================================
# 🥊 PvP 連線對戰系統防呆升級
# ==========================================
class MatchSession:
    def __init__(self, p1: discord.Member, p2: discord.Member, public_message: discord.Message):
        self.p1 = p1
        self.p2 = p2
        self.public_message = public_message
        self.p1_team = []
        self.p2_team = []
        self.p1_ready = False
        self.p2_ready = False
        self.cancelled = False

    async def check_start(self):
        if self.p1_ready and self.p2_ready:
            for i, c in enumerate(self.p1_team): c.name = f"攻{i+1}({c.name.split('(')[1]}"
            for i, c in enumerate(self.p2_team): 
                c.name = f"守{i+1}({c.name.split('(')[1]}"
                
            embed = discord.Embed(title="⚔️ 5v5 世紀大亂鬥 (PVP 盲選對決) ⚔️", description="雙方佈陣皆已就緒！點擊下方按鈕產生戰報。", color=discord.Color.gold())
            view = BattleControlView(self.p1_team, self.p2_team, embed)
            file = discord.File(fp=io.BytesIO(view.history_images[0]), filename="battle.png")
            embed.set_image(url="attachment://battle.png")
            
            await self.public_message.edit(content=f"🎉 **{self.p1.mention} VS {self.p2.mention} 戰鬥開始！**", embed=embed, attachments=[file], view=view)

class PVPTeamOrderView(SafeView):
    def __init__(self, session, user, chars):
        super().__init__(timeout=300)
        self.session = session
        self.user = user
        self.chars = chars
        self.selected_order = []
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        for i, char in enumerate(self.chars):
            is_selected = char in self.selected_order
            c_name = char.name.split('(')[1].replace(')','') if "(" in char.name else char.name
            label = f"{self.selected_order.index(char) + 1}. {c_name} ({char.role})" if is_selected else f"{c_name} ({char.role})"
            style = discord.ButtonStyle.primary if is_selected else discord.ButtonStyle.secondary
            
            def make_callback(c):
                async def cb(interaction):
                    await interaction.response.defer()
                    self.selected_order.append(c)
                    self.update_buttons()
                    await self.refresh_ui(interaction)
                return cb

            btn = discord.ui.Button(label=label, style=style, disabled=is_selected, custom_id=f"pvp_order_{i}", row=0 if i<3 else 1)
            btn.callback = make_callback(char)
            self.add_item(btn)

        reset_btn = discord.ui.Button(label="🔄 重設", style=discord.ButtonStyle.primary, row=2)
        async def reset_cb(interaction):
            await interaction.response.defer()
            self.selected_order.clear()
            self.update_buttons()
            await self.refresh_ui(interaction)
        reset_btn.callback = reset_cb
        self.add_item(reset_btn)

        if len(self.selected_order) == 5:
            confirm_btn = discord.ui.Button(label="✅ 確認出戰", style=discord.ButtonStyle.success, row=2)
            async def confirm_cb(interaction):
                await interaction.response.defer()
                if self.user == self.session.p1:
                    self.session.p1_team = self.selected_order
                    self.session.p1_ready = True
                else:
                    self.session.p2_team = self.selected_order
                    self.session.p2_ready = True
                await interaction.edit_original_response(content="✅ **準備完成！** 請回到主頻道等待對手。", view=None, embed=None)
                await self.session.check_start()
            confirm_btn.callback = confirm_cb
            self.add_item(confirm_btn)

        back_btn = discord.ui.Button(label="◀️ 上一頁 (重選角色)", style=discord.ButtonStyle.secondary, row=3)
        async def back_cb(interaction: discord.Interaction):
            await interaction.response.defer()
            view = PVPSelectView(self.session, self.user)
            await interaction.edit_original_response(content="🤫 歡迎來到準備室！請重新選擇你要出戰的角色：", embed=None, view=view)
        back_btn.callback = back_cb
        self.add_item(back_btn)

        cancel_btn = discord.ui.Button(label="❌ 取消對決", style=discord.ButtonStyle.danger, row=3)
        async def cancel_cb(interaction: discord.Interaction):
            await interaction.response.defer()
            self.session.cancelled = True
            await interaction.edit_original_response(content="🚫 你已取消這場對決。", view=None, embed=None)
            await self.session.public_message.edit(content=f"🚫 {interaction.user.mention} 取消了這場 PVP 對決。", view=None, embed=None)
        cancel_btn.callback = cancel_cb
        self.add_item(cancel_btn)

    async def refresh_ui(self, interaction: discord.Interaction):
        desc = "請點擊角色，決定出戰順序（對手看不到）：\n\n**👥 你的陣容：**\n"
        for c in self.chars:
            tags = ", ".join(c.tags) if c.tags else "無"
            c_name = c.name.split('(')[1].replace(')','') if "(" in c.name else c.name
            desc += f"🔸 **{c_name}** ({c.role}) | 特性: `{tags}`\n"

        desc += "\n**⚔️ 目前出戰順序：**\n"
        desc += " ➔ ".join([f"{c.name.split('(')[1].replace(')','')}({c.role})" for c in self.selected_order]) if self.selected_order else "尚未選擇..."
        
        embed = discord.Embed(title="⚙️ 秘密陣容配置", description=desc, color=discord.Color.purple())
        await interaction.edit_original_response(content="", embed=embed, view=self)

class PVPSelectView(SafeView):
    def __init__(self, session, user):
        super().__init__(timeout=300)
        self.session = session
        self.user = user
        self.team = []
        self.build_ui()

    def build_ui(self):
        self.clear_items()
        cat_options = get_categorized_options()
        
        if len(self.team) < 5:
            for cat_name, options in cat_options.items():
                if options:
                    max_sel = min(5, 5 - len(self.team))
                    sel = CategorySelect(f"從 {cat_name} 挑選...", options[:25], max_sel, self)
                    self.add_item(sel)

        confirm_btn = discord.ui.Button(label="✅ 確認出戰", style=discord.ButtonStyle.success, disabled=(len(self.team) != 5), row=4)
        confirm_btn.callback = self.on_confirm
        self.add_item(confirm_btn)
        
        clear_btn = discord.ui.Button(label="🗑️ 清空重選", style=discord.ButtonStyle.secondary, disabled=(len(self.team) == 0), row=4)
        clear_btn.callback = self.on_clear
        self.add_item(clear_btn)
        
        cancel_btn = discord.ui.Button(label="❌ 取消對決", style=discord.ButtonStyle.danger, row=4)
        cancel_btn.callback = self.on_cancel
        self.add_item(cancel_btn)

    def get_embed(self):
        embed = discord.Embed(title=f"🤫 盲選小黑屋 ({len(self.team)}/5)", description="對方看不見你的選擇，請安心挑選！\n*(💡 出手順序將完全依照你挑選的先後順序決定！)*", color=discord.Color.purple())
        if self.team:
            names = [char_db[cid]["name"] for cid in self.team]
            embed.add_field(name="目前陣容 (依出手順序)", value="\n".join([f"{i+1}. {name.split('．')[-1]}" for i, name in enumerate(names)]))
        return embed

    async def refresh_ui(self, interaction):
        self.build_ui()
        await interaction.edit_original_response(embed=self.get_embed(), view=self)

    async def on_clear(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.team = []
        await self.refresh_ui(interaction)

    async def on_confirm(self, interaction: discord.Interaction):
        await interaction.response.defer()
        prefix = "攻" if interaction.user == self.session.p1 else "守"
        chars = [SimpleCharacter(cid, prefix, char_db) for cid in self.team]
        
        # 👉 直接將選好順序的角色塞進 session，不再跳轉排序視窗
        if self.user == self.session.p1:
            self.session.p1_team = chars
            self.session.p1_ready = True
        else:
            self.session.p2_team = chars
            self.session.p2_ready = True
            
        await interaction.edit_original_response(content="✅ **準備完成！** 請回到主頻道等待對手。", view=None, embed=None)
        await self.session.check_start()

    async def on_cancel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.session.cancelled = True
        await interaction.edit_original_response(content="🚫 你已取消這場對決。", view=None, embed=None)
        await self.session.public_message.edit(content=f"🚫 {interaction.user.mention} 取消了這場 PVP 對決。", view=None, embed=None)

class PVPPrepRoomView(SafeView):
    def __init__(self, session):
        super().__init__(timeout=None)
        self.session = session

    @discord.ui.button(label="🚪 進入準備室 (僅限雙方)", style=discord.ButtonStyle.primary)
    async def btn_enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        if getattr(self.session, 'cancelled', False):
            await interaction.response.send_message("這場對決已經被取消了！", ephemeral=True)
            return
        if interaction.user not in [self.session.p1, self.session.p2]:
            await interaction.response.send_message("你不在這場對決名單中喔！", ephemeral=True)
            return
        if (interaction.user == self.session.p1 and self.session.p1_ready) or \
           (interaction.user == self.session.p2 and self.session.p2_ready):
            await interaction.response.send_message("你已經準備完成了，請等待對手！", ephemeral=True)
            return
        view = PVPSelectView(self.session, interaction.user)
        await interaction.response.send_message("🤫 歡迎來到準備室！請先選擇你要出戰的角色：", view=view, ephemeral=True)

    @discord.ui.button(label="❌ 取消對決", style=discord.ButtonStyle.danger)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in [self.session.p1, self.session.p2]:
            await interaction.response.send_message("只有發起人或受戰者可以取消對決！", ephemeral=True)
            return
        await interaction.response.defer()
        self.session.cancelled = True
        await interaction.edit_original_response(content=f"🚫 {interaction.user.mention} 取消了這場對決。", view=None)
        
class TrainingSetupView(SafeView):
    def __init__(self):
        super().__init__(timeout=300)
        self.team = []
        self.dummy_count = 5
        self.build_ui()

    def build_ui(self):
        self.clear_items()
        
        # 1. 攻擊方選角選單 (允許 1~5 隻，且過濾掉木樁本身)
        cat_options = get_categorized_options()
        if len(self.team) < 5:
            for cat_name, options in cat_options.items():
                if options:
                    max_sel = min(5, 5 - len(self.team))
                    sel = CategorySelect(f"從 {cat_name} 挑選...", options[:25], max_sel, self)
                    self.add_item(sel)

        # 2. 木樁數量設定下拉選單
        dummy_sel = discord.ui.Select(
            placeholder=f"🎯 目前設定：{self.dummy_count} 隻木樁",
            options=[
                discord.SelectOption(label="1 隻木樁 (測試單體爆發)", value="1", emoji="🎯"),
                discord.SelectOption(label="5 隻木樁 (測試群體 AOE)", value="5", emoji="🎳")
            ],
            row=3
        )
        
        async def dummy_cb(interaction: discord.Interaction):
            await interaction.response.defer()
            self.dummy_count = int(dummy_sel.values[0])
            await self.refresh_ui(interaction)
            
        dummy_sel.callback = dummy_cb
        self.add_item(dummy_sel)

        # 3. 控制按鈕
        confirm_btn = discord.ui.Button(label="⚔️ 開始打樁測試", style=discord.ButtonStyle.success, disabled=(len(self.team) == 0), row=4)
        confirm_btn.callback = self.on_confirm
        self.add_item(confirm_btn)
        
        clear_btn = discord.ui.Button(label="🗑️ 清空重選", style=discord.ButtonStyle.secondary, disabled=(len(self.team) == 0), row=4)
        clear_btn.callback = self.on_clear
        self.add_item(clear_btn)

    def get_embed(self):
        embed = discord.Embed(title=f"🪵 打樁訓練中心 ({len(self.team)}/5)", color=discord.Color.orange())
        if not self.team:
            embed.description = "請從下方選單挑選 1 ~ 5 名要測試的角色！\n並可以切換防守方的木樁數量。\n每回合木樁總共會對全體造成5%最大生命值真傷，\n傷害會受嘲諷影響也會觸發受擊次數。"
        else:
            names = [char_db[cid]["name"] for cid in self.team]
            embed.description = "**目前測試陣容：**\n" + "\n".join([f"{i+1}. {name}" for i, name in enumerate(names)])
            embed.description += f"\n\n🎯 **目標設定**：`{self.dummy_count} 隻木樁`"
        return embed

    async def refresh_ui(self, interaction):
        self.build_ui()
        await interaction.edit_original_response(embed=self.get_embed(), view=self)

    async def on_clear(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.team = []
        await self.refresh_ui(interaction)

    async def on_confirm(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # 建立攻擊方陣容與防守方木樁陣容
        from engine import SimpleCharacter
        atks = [SimpleCharacter(cid, "攻", char_db) for cid in self.team]
        defs = [SimpleCharacter("dummy", "守", char_db) for _ in range(self.dummy_count)]
        
        # 直接導入既有的 BattleControlView，完全沿用完美的戰報與結算圖表！
        from ui import BattleControlView
        embed = discord.Embed(title="⚔️ 打樁訓練中心 啟動 ⚔️", description="雙方已就緒，請點擊下方 [戰鬥開始] 進行模擬！", color=discord.Color.gold())
        view = BattleControlView(atks, defs, embed)
        await view.refresh_display(interaction)
