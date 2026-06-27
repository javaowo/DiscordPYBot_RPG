import discord #type: ignore
from discord.ext import commands #type: ignore
from discord import app_commands #type: ignore
import logging
from engine import char_db, BUFF_LIST, DEBUFF_LIST
from ui import SetupView, MatchSession, PVPPrepRoomView, TrainingSetupView, EFFECT_EMOJI_MAP

logging.getLogger("discord.gateway").setLevel(logging.WARNING)

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# ==========================================
# 📖 遊戲全域狀態與專有名詞辭典
# ==========================================
EFFECT_DESCRIPTIONS = {
    "增攻": "提升25%攻擊力",
    "增防": "提升25%防禦力",
    "免疫": "免疫後續添加的負面效果",
    "不屈": "若所受傷害大於現血量，最多減至1並獲得一回合「無敵」(生命為1時無法發動)",
    "治癒": "回合結束時恢復5%最大生命值",
    "護盾": "優先承受敵方造成的攻擊傷害，不承受效果傷害",
    "嘲諷": "敵人會優先攻擊帶有此效果的目標",
    "降雨": "同隊多人擁有時合併計算，由首位獲得者作為數值基準。每次受擊累積 1 點：\n> 1~5點：對敵方全體造成25%傷害\n> 6~10點：傷害提升至50%，我方恢復 25% 生命\n> 11~15點：傷害提升至75%，恢復量提升至50%\n> 15點以上：傷害提升至100%，恢復量提升至100%並驅散1個負面效果",
    "反傷": "反彈35%所受傷害，最多將目標扣至1血(無法致死)",
    "連擊": "以50%攻擊力再次施放相同技能",
    "免傷": "每層減少3%所受傷害，最多疊加5層",
    "抗寒": "免疫後續冰霜印記，回合結束時恢復3%最大生命值",
    "無敵": "所受傷害減至0",
    "金盾": "視為一種效果，同護盾但可抵擋效果傷害",
    "狂暴": "提升40%攻擊、降低60%防禦",
    "保護": "提升40%防禦、降低60%攻擊",
    "迴避": "敵方不會優先攻擊帶有此效果的目標",
    "醒目": "提升10%攻擊，免疫「暈眩」、「昏迷」、「魅惑」",
    "破甲": "攻擊有護盾的目標時，該目標承受傷害變為原來的1.5倍",

    "中毒": "回合結束對敵方造成5%最大生命值傷害",
    "暈眩": "無法行動",
    "昏迷": "無法行動，每次受到攻擊時有25%機率解除",
    "沈默": "只能使用普攻",
    "降攻": "減少35%攻擊力",
    "降防": "減少40%防禦力",
    "禁療": "無法恢復生命值",
    "封印": "角色被動技能失效",
    "壓制": "無法添加後續的正面效果",
    "魅惑": "只能使用普攻攻擊自己",
    "易傷": "提升25%受到的傷害",
    "灼傷": "減少10%防禦，回合結束造成3%最大生命值傷害",
    "冰凍": "減少10%防禦且無法行動",
    "受損": "每層提升3%易傷，最多疊加5層",
    "灼燒": "回合結束時，每層造成3%最大生命值傷害，最多疊加5層",
    "冰霜": "每層提升3%無法行動機率，最多疊加5層",
    "鎖定": "敵方會優先攻擊帶有此效果的目標",
    "詛咒": "所有的治療效果皆反轉為真實傷害",
    
    "結算": "一次釋放所有剩餘回合數的傷害/治療效果",
    "淨化": "移除負面效果",
    "驅散": "移除正面效果",
    "真實傷害": "此傷害無視防禦",
    "攤傷": "將傷害平均分攤給指定目標",
    "領域展開": "領域展開效果在場上最多存在一個，若後續有領域展開效果則會覆蓋前一個效果（不分敵我）",
}

@bot.event
async def on_ready():
    await bot.tree.sync()
    print("✅ 5v5 終極對戰系統上線！")

class HelpPaginationView(discord.ui.View):
    def __init__(self, embeds):
        super().__init__(timeout=180)
        self.embeds = embeds
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.children[0].disabled = self.current_page == 0
        self.children[1].label = f"第 {self.current_page + 1} / {len(self.embeds)} 頁"
        self.children[2].disabled = self.current_page == len(self.embeds) - 1

    @discord.ui.button(label="上一頁", style=discord.ButtonStyle.primary, custom_id="prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="第 X 頁", style=discord.ButtonStyle.secondary, disabled=True, custom_id="indicator")
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 這個按鈕只是用來顯示文字的，所以點擊不用有反應
        pass

    @discord.ui.button(label="下一頁", style=discord.ButtonStyle.primary, custom_id="next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

@bot.tree.command(name="help", description="查看遊戲玩法、指令與全域狀態百科")
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    
    # 【第一頁：遊戲介紹】
    embed1 = discord.Embed(title="📖 5v5 終極對戰系統 - 遊戲介紹", color=discord.Color.blue())
    embed1.description = (
        "歡迎來到全自動戰鬥競技場！\n\n"
        "在這裡，你可以挑選 5 名各具特色的角色組成小隊，系統將會為你自動推演整場戰鬥，直到一方全滅為止。\n\n"
        "每位角色都有獨特的「普攻」、「小招」、「大招」與「被動」。"
        "善用不同的角色定位（如坦克吸傷、輔助淨化、輸出爆發）來克制對手的陣容吧！"
    )
    
    # 【第二頁：指令說明】
    embed2 = discord.Embed(title="🎮 常用指令一覽", color=discord.Color.green())
    for cmd in bot.tree.get_commands():
        # if cmd.name in ["test", "dev_only"]: continue（排除想隱藏的指令）
        embed2.add_field(name=f"`/{cmd.name}`", value=cmd.description, inline=False)

    # 【第三頁：狀態效果一覽】
    embed3 = discord.Embed(title="✨ 全域狀態與名詞百科", color=discord.Color.gold())
    
    buff_texts, debuff_texts = [], []
    for eff, desc in EFFECT_DESCRIPTIONS.items():
        emoji = EFFECT_EMOJI_MAP.get(eff, "📌")
        line_text = f"{emoji} **{eff}**：{desc}"
        
        if eff in BUFF_LIST: buff_texts.append(line_text)
        elif eff in DEBUFF_LIST: debuff_texts.append(line_text)
        else: buff_texts.append(line_text)

    buff_str = "\n".join(buff_texts)
    debuff_str = "\n".join(debuff_texts)
    
    embed3.add_field(name="📈 正面狀態 (Buff)", value=buff_str[:1024], inline=False)
    embed3.add_field(name="📉 負面狀態 (Debuff)", value=debuff_str[:1024], inline=False)

    embeds = [embed1, embed2, embed3]
    view = HelpPaginationView(embeds)
    await interaction.followup.send(embed=embeds[0], view=view)

class InfoSelect(discord.ui.Select):
    def __init__(self, placeholder, options):
        super().__init__(placeholder=placeholder, options=options)

    async def callback(self, interaction: discord.Interaction):
        cid = self.values[0]
        data = char_db[cid]
        
        # --- 這裡完全沿用你原本完美的 Embed 生成邏輯 ---
        embed = discord.Embed(title=f"📜 角色檔案：【{data['name']}】", color=discord.Color.gold())
        tags_str = ", ".join(data.get("tags", [])) if data.get("tags") else "無"
        role_str = data.get("role", "未知定位")
        
        stats_text = f"🏷️ 定位：`{role_str}`\n"
        stats_text += f"🔖 特性：`{tags_str}`\n"
        stats_text += f"❤️ 生命值：`{data['hp']}`\n⚔️ 攻擊力：`{data['atk']}`\n🛡️ 防禦力：`{data['defense']}`"
        embed.add_field(name="📊 基礎屬性", value=stats_text, inline=False)
        
        def format_skill(s_data, category):
            desc = ""
            if category in ["small", "ultimate"]:
                cd = s_data.get("cd", 0)
                initial_cd = s_data.get("initial_cd", 0)
                cd_text = f"⏳ **冷卻**：{cd} 回合"
                if initial_cd > 0: cd_text += f" *(第 {initial_cd} 回合首發)*"
                desc += cd_text + "\n"
            if category == "passive":           
                p_cd = s_data.get("cd", 0)
                if p_cd > 0: desc += f"⏳ **冷卻**：{p_cd} 回合\n"
            if "description" in s_data:
                desc += f"💡 **敘述**：{s_data['description']}\n"
            return desc

        skills = data["skills"]
        embed.add_field(name="🗡️ 【普攻】", value=format_skill(skills["normal"], "normal"), inline=False)
        embed.add_field(name=f"✨ 【小招】{skills['small'].get('name', '')}", value=format_skill(skills["small"], "small"), inline=False)
        embed.add_field(name=f"🔥 【大招】{skills['ultimate'].get('name', '')}", value=format_skill(skills["ultimate"], "ultimate"), inline=False)
        
        all_skill_texts = f"{skills['normal'].get('description', '')} {skills['small'].get('description', '')} {skills['ultimate'].get('description', '')}"
        if "passive" in skills:
            embed.add_field(name=f"🛡️ 【被動】{skills['passive'].get('name', '')}", value=format_skill(skills["passive"], "passive"), inline=False)
            all_skill_texts += f" {skills['passive'].get('description', '')}"

        found_effects = []
        for effect, desc in EFFECT_DESCRIPTIONS.items():
            if effect in all_skill_texts:
                emoji = EFFECT_EMOJI_MAP.get(effect, "📌") 
                found_effects.append(f"{emoji} **{effect}**：{desc}")
                
        if found_effects:
            effects_str = "\n".join(found_effects)
            if len(effects_str) > 1024: effects_str = effects_str[:1020] + "..."
            embed.add_field(name="📖 狀態與名詞解釋", value=effects_str, inline=False)

        await interaction.response.edit_message(content=f"✅ 已為您載入 **{data['name']}** 的情報：", embed=embed, view=self.view)


class InfoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
        categories = {
            "🛡️ 一般攻擊區": ["戰士", "刺客", "法師"],
            "🔮 團隊輔助區": ["坦克", "輔助"],
            "💖 特殊職業區": ["繪域師", "控場者"]
        }
        
        sorted_chars = sorted(char_db.items(), key=lambda x: x[1]['name'])
        
        for cat_name, roles in categories.items():
            options = []
            for cid, data in sorted_chars:
                if cid == "dummy": continue
                if data.get("role") in roles:
                    role = data.get("role", "未知")
                    tags = ", ".join(data.get("tags", []))
                    desc = f"特性：{tags}" if tags else "無"
                    
                    options.append(discord.SelectOption(
                        label=f"[{role}] {data['name']}"[:100],
                        description=desc[:100],
                        value=cid
                    ))
            
            if options:
                self.add_item(InfoSelect(placeholder=f"請選擇 {cat_name} 角色...", options=options[:25]))


@bot.tree.command(name="info", description="開啟角色情報庫，查看所有角色的詳細數值與技能說明")
async def info(interaction: discord.Interaction):
    await interaction.response.defer()
    view = InfoView()
    await interaction.followup.send("🔍 **歡迎來到對戰競技場情報庫！**\n請從下方的分類選單中，挑選您想查看的角色：", view=view)

@bot.tree.command(name="play5v5", description="開啟一場 5v5 全自動對戰")
async def play5v5(interaction: discord.Interaction):
    await interaction.response.defer()
    view = SetupView()
    await interaction.followup.send("請透過下方下拉選單，挑選**攻擊方**的 5 隻角色：", view=view)
    
@bot.tree.command(name="training", description="開啟打樁訓練中心，測試單體或群體隊伍傷害")
async def training_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    view = TrainingSetupView()
    await interaction.followup.send(embed=view.get_embed(), view=view)

@bot.tree.command(name="pvp", description="向另一位玩家發起 5v5 盲選決鬥！")
async def pvp_challenge(cmd_inter: discord.Interaction, opponent: discord.Member):
    if opponent == cmd_inter.user:
        await cmd_inter.response.send_message("你不能挑戰自己啦！", ephemeral=True)
        return
    if opponent.bot:
        await cmd_inter.response.send_message("你不能挑戰機器人！", ephemeral=True)
        return

    view = discord.ui.View()
    accept_btn = discord.ui.Button(label="接受挑戰 🥊", style=discord.ButtonStyle.success)
    reject_btn = discord.ui.Button(label="拒絕 / 收回挑戰 ❌", style=discord.ButtonStyle.danger)
    
    async def accept_callback(interaction: discord.Interaction):
        if interaction.user != opponent:
            await interaction.response.send_message("這不是給你的挑戰書喔！", ephemeral=True)
            return
            
        public_message = interaction.message
        if public_message is None:
            await interaction.response.send_message("無法讀取挑戰訊息，請稍後再試。", ephemeral=True)
            return
            
        challenger = cmd_inter.user 
        
        if not isinstance(challenger, discord.Member) and cmd_inter.guild is not None:
            challenger = cmd_inter.guild.get_member(challenger.id)
        if not isinstance(challenger, discord.Member):
            await interaction.response.send_message("無法取得你的會員資料，請在伺服器內執行此指令。", ephemeral=True)
            return
            
        session = MatchSession(challenger, opponent, public_message)
        prep_view = PVPPrepRoomView(session)
        
        await interaction.response.edit_message(content=f"⏳ {challenger.mention} 與 {opponent.mention} 的決鬥已成立！\n請雙方點擊下方按鈕進入小黑屋進行盲選。", view=prep_view)

    async def reject_callback(interaction: discord.Interaction):
        if interaction.user == opponent:
            await interaction.response.edit_message(content=f"🚫 {opponent.mention} 婉拒了 {cmd_inter.user.mention} 的挑戰。", view=None)
        elif interaction.user == cmd_inter.user:
            await interaction.response.edit_message(content=f"🚫 {cmd_inter.user.mention} 收回了挑戰書。", view=None)
        else:
            await interaction.response.send_message("這不關你的事喔！", ephemeral=True)

    accept_btn.callback = accept_callback
    reject_btn.callback = reject_callback
    view.add_item(accept_btn)
    view.add_item(reject_btn)
    await cmd_inter.response.send_message(f"🥊 {cmd_inter.user.mention} 向 {opponent.mention} 發起了決鬥！\n請 {opponent.mention} 選擇是否接受：", view=view)

bot.run("YOUR_BOT_TOKEN")
