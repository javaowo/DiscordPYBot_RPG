import json
import random

with open('characters.json', 'r', encoding='utf-8') as f:
    char_db = json.load(f)

# ==========================================
# 🌟 全域狀態註冊中心 (動態判定 Buff/Debuff)
# ==========================================
BUFF_LIST = [
    "增攻", "增防", "免疫", "不屈", "治癒", "嘲諷", "降雨", "反傷", "連擊", "抗寒",
    "無敵", "狂暴", "保護", "迴避", "醒目", "破甲"
]

DEBUFF_LIST = [
    "中毒", "暈眩", "昏迷", "沈默", "降攻", "降防", "禁療", "封印", "壓制", "魅惑",
    "易傷", "灼傷", "冰凍", "鎖定", "詛咒", "音樂"
]


# ==========================================
# ⚙️ 專屬機制總管 (Mechanics Hub)
# ==========================================

def process_special_skill(tag, attacker, target, base_mult, base_chance, alive_enemies, is_primary=False):
    """【發動前】修改技能的倍率與機率"""
    new_mult = base_mult
    new_chance = base_chance

    if tag == "yinyu_small":
        buff_count = min(5, sum(1 for e in target.effects if e in BUFF_LIST))
        debuff_count = min(5, sum(1 for e in target.effects if e in DEBUFF_LIST))
        new_mult += (buff_count * 0.05)
        new_chance += (debuff_count * 5)
        
    elif tag == "yinyu_ult":
        if len(alive_enemies) == 1:
            new_mult, new_chance = 2.5, 25
        else:
            new_mult = 1.5 if is_primary else 1.0
            new_chance = 15

    return new_mult, new_chance


def execute_special_skill(tag, attacker, caster, targets, log_lines, allies=None):
    """【發動後】執行額外的技能效果與特殊機制"""
    
    if tag == "dummy_normal":
        dummy_count = len([a for a in allies if a.hp > 0]) if allies else 1
        taunted_chars = [t for t in targets if "嘲諷" in t.effects or "鎖定" in t.effects]
        if taunted_chars:
            for t in taunted_chars:
                dmg_pct = 0.15 / dummy_count
                dmg_amt = max(1, int(t.max_hp * dmg_pct))
                t.take_damage(attacker=caster, base_damage=dmg_amt, is_true_damage=True)
        else:
            dmg_pct = 0.05 / dummy_count
            for t in targets:
                dmg_amt = max(1, int(t.max_hp * dmg_pct))
                t.take_damage(attacker=caster, base_damage=dmg_amt, is_true_damage=True)
    
    elif tag == "mingyu_small":
        shield_amount = int(caster.defense * 0.75)
        log_lines.append(f" 🛡️ 全隊獲得一回合 [增防] ")
        for t in targets:
            if t.hp > 0:
                t.add_effect("增防", 1, log_lines, silent=True)
                t.shield_hp += shield_amount
        log_lines.append(f" 🛡️ 全隊獲得了 `{shield_amount}` 點 [護盾]")

    elif tag == "mingyu_ult":
        shield_amount = int(caster.defense * 1.5)
        log_lines.append(f" 🛡️ 全隊獲得兩回合 [增防] ")
        for t in targets:
            if t.hp > 0:
                target_debuffs = [k for k in t.effects.keys() if k in DEBUFF_LIST]
                if target_debuffs:
                    removed = random.choice(target_debuffs)
                    del t.effects[removed]
                    if removed in getattr(t, "effect_stacks", {}): del t.effect_stacks[removed]
                    log_lines.append(f" 💨 **{t.name}** 被淨化了 [{removed}] 狀態")
                
                t.add_effect("增防", 2, log_lines, silent=True)
                t.shield_hp += shield_amount
        log_lines.append(f" 🛡️ 全隊獲得了 `{shield_amount}` 點 [護盾]")

    elif tag == "yamian_small" and allies:
        heal_amt = int(caster.get_current_atk() * 1.0)
        for a in allies:
            if a.hp > 0:
                a.apply_heal(heal_amt, log_lines, caster)
                
        passive_heal = int(heal_amt * 0.5)
        actual_passive = caster.apply_heal(passive_heal, log_lines, caster)
        if actual_passive > 0:
            log_lines.append(f" 💖 **{caster.name}** 觸發被動，額外恢復 `{actual_passive}` 點生命")

    elif tag == "yamian_ult" and allies:
        log_lines.append(f" ✨ 全隊獲得兩回合 [治癒]")
        for a in allies:
            if a.hp > 0: a.add_effect("治癒", 2, log_lines, silent=True)

    elif tag == "lingyu_small" and allies:
        log_lines.append(f" 🛡️ 全隊獲得兩回合 [增攻] 與 [醒目]")
        for a in allies:
            if a.hp > 0:
                a.add_effect("增攻", 2, log_lines, silent=True)
                a.add_effect("醒目", 2, log_lines, silent=True)
                
    elif tag == "lingyu_ult" and allies:
        log_lines.append(f" 🛡️ 全隊獲得兩回合 [不屈] 與 [治癒]")
        for a in allies:
            if a.hp > 0:
                a.add_effect("不屈", 2, log_lines, silent=True)
                a.add_effect("治癒", 2, log_lines, silent=True)

    elif tag == "youda_ult":
        for t in targets:
            if t.hp > 0 and "中毒" in t.effects:
                duration = t.effects["中毒"]
                poison_dmg = int(t.max_hp * 0.05 * duration)
                del t.effects["中毒"]
                if "中毒" in getattr(t, "effect_stacks", {}): del t.effect_stacks["中毒"]
                
                dmg, p_logs = t.take_damage(attacker=caster, base_damage=poison_dmg, is_true_damage=True)
                log_lines.append(f" 💥 **{caster.name}** 引爆毒素，結算 `{duration}` 回合中毒")
                log_lines.append(f" └ 擊中 **{t.name}**，造成 `{dmg}` 點真實傷害")
                log_lines.extend(p_logs)

    elif tag == "yemo_ult":
        for t in targets:
            if t.hp > 0 and random.randint(1, 100) <= 60:
                if getattr(t, "passive", None) and getattr(t.passive, "special_tag", None) == "xinyue_passive":
                    log_lines.append(f" ✨ **{t.name}** 觸發 [星月加護]，免疫了冷卻重置")
                else:
                    if getattr(t, "small_skill", None): t.small_skill.current_cd = t.small_skill.cd
                    if getattr(t, "ult_skill", None): t.ult_skill.current_cd = t.ult_skill.cd
                    log_lines.append(f" 🕰️ **{t.name}** 受到秋色干擾，所有技能冷卻被重置了")
                    
    elif tag == "xinyue_small" and allies:
        shield_amount = int(caster.get_current_atk() * 0.5)
        for a in allies:
            if a.hp > 0:
                a.shield_hp += shield_amount
        log_lines.append(f" 🛡️ 全隊獲得了 `{shield_amount}` 點 [護盾]")
                
    elif tag == "xinyue_ult":
        if allies:
            log_lines.append(f" 🌙 全隊獲得兩回合 [免疫]")
            for a in allies:
                if a.hp > 0: a.add_effect("免疫", 2, log_lines, silent=True)
                
        log_lines.append(f" ⛓️ 敵方全體被附加了兩回合 [壓制]")
        for t in targets:
            if t.hp > 0: t.add_effect("壓制", 2, log_lines, silent=True)

    elif tag == "yunya_normal":
        consumed = int(caster.hp * 0.03)
        caster.hp -= consumed
        for t in targets:
            if t.hp > 0:
                dmg, p_logs = t.take_damage(attacker=caster, base_damage=consumed, is_true_damage=True)
                log_lines.append(f" └ 擊中 **{t.name}**，造成 `{dmg}` 點真實傷害")
                log_lines.extend(p_logs)

    elif tag == "yunya_ult":
        consumed = int(caster.hp * 0.5)
        caster.hp -= consumed
        log_lines.append(f" 🩸 **{caster.name}** 獻祭了 `{consumed}` 點生命值")
        for t in targets:
            if t.hp > 0:
                dmg, p_logs = t.take_damage(attacker=caster, base_damage=consumed, is_true_damage=True)
                log_lines.append(f" └ 擊中 **{t.name}**，造成 `{dmg}` 點真實傷害")
                log_lines.extend(p_logs)
                
    elif tag == "yangyu_ult":
        all_field_chars = allies + targets 
        for t in all_field_chars:
            if t.hp <= 0: continue
            target_debuffs = [k for k in t.effects.keys() if k in DEBUFF_LIST]
            if target_debuffs:
                for debuff in target_debuffs:
                    del t.effects[debuff]
                    if debuff in getattr(t, "effect_stacks", {}): del t.effect_stacks[debuff]
                log_lines.append(f" ✨ **{t.name}** 身上的 [{', '.join(target_debuffs)}] 被淨化了")
                
            if t == caster: continue
            
            if t in allies:
                if t.small_skill.current_cd > 0: t.small_skill.current_cd -= 1
                if t.ult_skill.current_cd > 0: t.ult_skill.current_cd -= 1
                log_lines.append(f" ⏳ **{t.name}** 的所有技能冷卻 [減少 1 回合]")
            else:
                t.small_skill.current_cd += 1
                t.ult_skill.current_cd += 1
                log_lines.append(f" ⛓️ **{t.name}** 的所有技能冷卻 [延長 1 回合]")
                
    elif tag == "yangyu_small":
        caster.add_effect("嘲諷", 2, log_lines)
        caster.add_effect("治癒", 2, log_lines)

    elif tag == "yangyu_normal":
        if random.randint(1, 100) <= 35:
            caster.add_effect("嘲諷", 1, log_lines)

    elif tag == "yuehong_normal":
        for t in targets:
            if t.hp > 0:
                dmg, p_logs = t.take_damage(attacker=caster, base_damage=int(caster.get_current_atk() * 0.75))
                log_lines.append(f" └ 擊中 **{t.name}**，造成 `{dmg}` 傷害")
                log_lines.extend(p_logs)
                
                if dmg > 0:
                    heal_amt = dmg
                    if "降雨" in caster.effects and getattr(caster, "passive", None) and caster.passive.special_tag == "yuehong_passive":
                        heal_amt = int(heal_amt * 1.5)
                    actual_heal = caster.apply_heal(heal_amt, log_lines, caster)
                    if actual_heal > 0:
                        log_lines.append(f" 🩸 **{caster.name}** 吸收傷害，恢復 `{actual_heal}` 點生命")

    elif tag == "yuehong_small":
        for t in targets:
            if t.hp <= 0: continue
            
            dmg1, p_logs1 = t.take_damage(attacker=caster, base_damage=int(caster.get_current_atk() * 0.5), is_true_damage=True)
            log_lines.append(f" └ (真傷)擊中 **{t.name}**，造成 `{dmg1}` 點真實傷害")
            log_lines.extend(p_logs1)

            if t.hp > 0:
                dmg2, p_logs2 = t.take_damage(attacker=caster, base_damage=int(caster.get_current_atk() * 0.75))
                log_lines.append(f" └ 擊中 **{t.name}**，造成 `{dmg2}` 傷害")
                log_lines.extend(p_logs2)
                
                target_buffs = [k for k in t.effects.keys() if k in BUFF_LIST]
                if target_buffs:
                    stolen = random.choice(target_buffs)
                    duration = t.effects[stolen]
                    stacks = getattr(t, "effect_stacks", {}).get(stolen, 1)
                    del t.effects[stolen]
                    if stolen in getattr(t, "effect_stacks", {}): del t.effect_stacks[stolen]
                    
                    caster.add_effect(stolen, duration, log_lines)
                    if stacks > 1: caster.effect_stacks[stolen] = stacks
                    log_lines.append(f" └ 💧 成功竊取 [{stolen}]")
                    
            if t.hp > 0:
                dmg3, p_logs3 = t.take_damage(attacker=caster, base_damage=int(caster.get_current_atk() * 1.0))
                log_lines.append(f" └ 擊中 **{t.name}**，造成 `{dmg3}` 傷害！")
                log_lines.extend(p_logs3)
                
                if dmg3 > 0 and allies:
                    heal_amt = dmg3
                    if "降雨" in caster.effects and getattr(caster, "passive", None) and caster.passive.special_tag == "yuehong_passive":
                        heal_amt = int(heal_amt * 1.5)

                    log_lines.append(f" 💚 **{caster.name}** 將水流轉化，全隊恢復了 `{heal_amt}` 點生命！")

                    dummy_logs = [] 
                    for a in allies:
                        if a.hp > 0:
                            a.apply_heal(heal_amt, dummy_logs, caster)

    elif tag == "yuehong_ult":
        caster.add_effect("降雨", 3, log_lines)
        
        base_dmg = int(caster.get_current_atk() * 1.3)
        target_dmg_map = {}
        p_logs_acc = []

        for t in targets:
            if t.hp > 0:
                dmg, p_logs = t.take_damage(attacker=caster, base_damage=base_dmg)
                target_dmg_map[t] = dmg
                p_logs_acc.extend(p_logs)
                
                if random.randint(1, 100) <= 25:
                    t.add_effect("封印", 2, p_logs_acc)
                    
        total_overall = sum(target_dmg_map.values())
        if total_overall > 0:
            if len(target_dmg_map) > 1:
                log_lines.append(f" └ 對 **全體目標** 總計造成 `{total_overall}` 傷害！")
            else:
                for t, dmg in target_dmg_map.items():
                    log_lines.append(f" └ 擊中 **{t.name}**，總計造成 `{dmg}` 傷害！")
                    
        log_lines.extend(p_logs_acc)
                    
    elif tag == "jiyu_ult":
        for t in targets:
            if t.hp > 0:
                extended_debuffs = []
                for eff in list(t.effects.keys()):
                    if eff in DEBUFF_LIST and t.effects[eff] != 999:
                        t.effects[eff] += 1
                        extended_debuffs.append(eff)
                
                if extended_debuffs:
                    log_lines.append(f" 🌀 靜語細拂吹過，**{t.name}** 的 [{', '.join(extended_debuffs)}] 延長了 1 回合")
                    
    elif tag == "yuhe_normal":
        if random.randint(1, 100) <= 25:
            extended = []
            for eff, duration in list(caster.effects.items()):
                if duration != 999:
                    caster.effects[eff] += 1
                    extended.append(eff)
            if extended:
                log_lines.append(f" ⏳ **{caster.name}** 身上的 [{', '.join(extended)}] 皆延長了 1 回合")

    elif tag == "yuhe_small":
        caster.add_effect("嘲諷", 2, log_lines)
        caster.add_effect("反傷", 2, log_lines)
        
    elif tag == "yuhe_ult" and allies:
        alive_allies = [a for a in allies if a.hp > 0]
        if alive_allies:
            target_allies = set([
                max(alive_allies, key=lambda x: x.atk),
                max(alive_allies, key=lambda x: x.max_hp),
                max(alive_allies, key=lambda x: x.defense)
            ])
            
            log_lines.append(f" 🌌 核心隊員獲得兩回合 [增防] 與 [增攻]")
            for a in target_allies:
                debuffs = [k for k in a.effects.keys() if k in DEBUFF_LIST]
                if debuffs:
                    for d in debuffs:
                        del a.effects[d]
                        if d in getattr(a, "effect_stacks", {}): del a.effect_stacks[d]
                    log_lines.append(f" ✨ **{a.name}** 身上的 [{', '.join(debuffs)}] 被淨化了")
                
                a.add_effect("增攻", 2, log_lines, silent=True)
                a.add_effect("增防", 2, log_lines, silent=True)
                
    elif tag == "xinqiao_small":
        caster.add_effect("連擊", 1, log_lines)
        
    elif tag == "xinqiao_ult":
        caster.add_effect("降雨", 2, log_lines)

    elif tag == "niyu_small":
        for t in targets:
            if t.hp <= 0: continue
            for _ in range(2):
                if random.randint(1, 100) <= 25:
                    if "中毒" in t.effects:
                        t.effects["中毒"] += 1
                        log_lines.append(f" ☠️ **{t.name}** 身上的 [中毒] 延長了 1 回合！")
                    else:
                        t.add_effect("中毒", 2, log_lines)

    elif tag == "niyu_ult":
        for t in targets:
            if t.hp > 0:
                effects_to_remove = list(t.effects.keys())
                if effects_to_remove:
                    # 計算真實傷害 (每個效果 = 5% 最大生命)
                    detonate_dmg = int(t.max_hp * 0.05 * len(effects_to_remove))
                    
                    # 💥 引爆 = 清空身上所有狀態與層數
                    t.effects.clear()
                    if hasattr(t, "effect_stacks"): t.effect_stacks.clear()
                    
                    ddmg, p_logs = t.take_damage(attacker=caster, base_damage=detonate_dmg, is_true_damage=True)
                    log_lines.append(f" 💥 **{caster.name}** 引爆了 **{t.name}** 身上的 {len(effects_to_remove)} 個效果，造成 `{ddmg}` 真實傷害！")
                    log_lines.extend(p_logs)
                    
    elif tag == "qiya_ult":
        caster.add_effect("迴避", 2, log_lines)
        
    elif tag == "yechen_normal":
        shield_val = caster.get_current_atk()
        caster.add_effect("護盾", 999, log_lines, value=shield_val)

    # 🪵 曄宸小招：椅上回憶 (竊取嘲諷)
    elif tag == "yechen_small":
        stolen_success = False
        
        # 優先搜尋敵方是否有嘲諷
        for e in (allies if allies else []): # 在傳入的對手/隊友名單中搜尋
            if "嘲諷" in e.effects and e.hp > 0:
                # 偷取：清除對方的嘲諷，並記錄剩餘回合數
                rem_duration = e.effects["嘲諷"]
                del e.effects["嘲諷"]
                if "嘲諷" in getattr(e, "effect_stacks", {}): del e.effect_stacks["嘲諷"]
                
                # 給予自己並延長 1 回合
                caster.add_effect("嘲諷", rem_duration + 1, log_lines)
                log_lines.append(f" 🪑 **{caster.name}** 喚醒回憶，強行奪取了敵方 **{e.name}** 身上的 [嘲諷]！")
                stolen_success = True
                break
                
        # 若敵方沒有，搜尋我方隊友是否有嘲諷 (避開自己)
        if not stolen_success:
            # 這裡需要傳入我方全體，你可以從主迴圈那邊抓
            all_allies = [c for c in (targets + [caster]) if c.hp > 0 and c != caster]
            for a in all_allies:
                if "嘲諷" in a.effects:
                    rem_duration = a.effects["嘲諷"]
                    del a.effects["嘲諷"]
                    if "嘲諷" in getattr(a, "effect_stacks", {}): del a.effect_stacks["嘲諷"]
                    
                    caster.add_effect("嘲諷", rem_duration + 1, log_lines)
                    log_lines.append(f" 🪑 **{caster.name}** 接替防線，吸收了隊友 **{a.name}** 身上的 [嘲諷]！")
                    stolen_success = True
                    break

        # 根據竊取結果給予對應獎勵
        if stolen_success:
            caster.add_effect("免傷", 999, log_lines)
        else:
            # 竊取失敗，單純給自己兩回合嘲諷
            caster.add_effect("嘲諷", 2, log_lines)

    # 🪵 曄宸大招：千秋萬語 (扣血轉盾)
    elif tag == "yechen_ult":
        if caster.hp > 1:
            # 折損現有 25% 生命
            hp_loss = int(caster.hp * 0.25)
            caster.hp = max(1, caster.hp - hp_loss)
            log_lines.append(f" 🩸 **{caster.name}** 折損了 `{hp_loss}` 點現有生命，凝聚為歲月之盾！")
            
            # 轉為等值護盾
            caster.add_effect("護盾", 999, log_lines, value=hp_loss)
            
        # 獲得兩回合抗寒與治癒
        caster.add_effect("抗寒", 2, log_lines)
        caster.add_effect("治癒", 2, log_lines)

def check_special_passive(tag, defender, attacker):
    """【被動判定】檢查特殊被動是否滿足觸發條件"""
    if tag == "lingyu_passive":
        return defender.hp < (defender.max_hp * 0.1)
    if tag == "yemo_passive":
        return defender.hp < (defender.max_hp * 0.5)
    return True


# ==========================================
# 📊 資料類別 (Data Classes)
# ==========================================

class GamePassive:
    def __init__(self, name, trigger, chance, effect, max_triggers=999, special_tag=None, effect_duration=2, max_triggers_per_battle=999, cd=0):
        self.name = name
        self.trigger = trigger
        self.chance = chance
        self.effect = effect
        self.max_triggers = max_triggers
        self.special_tag = special_tag
        self.effect_duration = effect_duration
        self.max_triggers_per_battle = max_triggers_per_battle
        self.cd = cd

class GameSkill:
    def __init__(self, name, category, multiplier, cd=0, initial_cd=0, target_type="single", hits=1, effect="none", effect_value=0, damage_type="normal", effect_chance=100, special_tag=None, effect_duration=2, apply_effect_first=False, is_split_damage=False, target_count=0, apply_effect_per_hit=False):
        self.name = name
        self.category = category
        self.multiplier = multiplier
        self.cd = cd
        self.current_cd = initial_cd
        self.target_type = target_type 
        self.hits = hits
        self.effect = effect
        self.effect_value = effect_value
        self.damage_type = damage_type
        self.effect_chance = effect_chance
        self.special_tag = special_tag
        self.effect_duration = effect_duration
        self.apply_effect_first = apply_effect_first
        self.is_split_damage = is_split_damage
        self.target_count = target_count
        self.apply_effect_per_hit = apply_effect_per_hit

# ==========================================
# ⚔️ 角色實體與核心運算邏輯
# ==========================================

class SimpleCharacter:
    def __init__(self, cid, prefix, char_db):
        data = char_db.get(cid, {})
        self.cid = cid
        raw_name = data.get("name", "未知角色")
        self.full_name = raw_name
        short_name = raw_name.split('．')[-1] if '．' in raw_name else raw_name
        self.name = f"{prefix}({short_name})"
        self.max_hp = data["hp"]
        self.hp = data["hp"]
        self.atk = data["atk"]
        self.defense = data["defense"]
        self.role = data.get("role", "未知定位")
        self.tags = data.get("tags", [])
        
        self.effects = {}
        self.effect_stacks = {}
        self.shield_hp = 0
        self.newly_applied_this_turn = set()
        
        self.stats_dmg_dealt = 0
        self.stats_healing_done = 0
        self.stats_dmg_taken = 0
        
        skills = data["skills"]
        n_data = skills["normal"]
        s_data = skills["small"]
        u_data = skills["ultimate"]
        p_data = skills.get("passive")

        self.normal_skill = GameSkill(
            n_data["name"], "normal", n_data["multiplier"], 
            damage_type=n_data.get("damage_type", "normal"), 
            special_tag=n_data.get("special_tag"), 
            effect=n_data.get("effect", "none"), 
            effect_chance=n_data.get("effect_chance", 100), 
            effect_duration=n_data.get("effect_duration", 2), 
            apply_effect_first=n_data.get("apply_effect_first", False), 
            is_split_damage=n_data.get("is_split_damage", False), 
            target_count=n_data.get("target_count", 0),
            apply_effect_per_hit=n_data.get("apply_effect_per_hit", False)
        )
        
        self.small_skill = GameSkill(
            s_data["name"], "small", s_data["multiplier"], 
            cd=s_data.get("cd", 4), initial_cd=s_data.get("initial_cd", 1), 
            target_type=s_data.get("target_type", "single"), hits=s_data.get("hits", 1), 
            effect=s_data.get("effect", "none"), effect_value=s_data.get("effect_value", 0), 
            damage_type=s_data.get("damage_type", "normal"), effect_chance=s_data.get("effect_chance", 100), 
            special_tag=s_data.get("special_tag"), effect_duration=s_data.get("effect_duration", 2), 
            apply_effect_first=s_data.get("apply_effect_first", False), 
            is_split_damage=s_data.get("is_split_damage", False), target_count=s_data.get("target_count", 0),
            apply_effect_per_hit=s_data.get("apply_effect_per_hit", False)
        )

        self.ult_skill = GameSkill(
            u_data["name"], "ultimate", u_data["multiplier"], 
            cd=u_data.get("cd", 4), initial_cd=u_data.get("initial_cd", 2), 
            target_type=u_data.get("target_type", "single"), hits=u_data.get("hits", 1), 
            effect=u_data.get("effect", "none"), effect_value=u_data.get("effect_value", 0), 
            damage_type=u_data.get("damage_type", "normal"), effect_chance=u_data.get("effect_chance", 100), 
            special_tag=u_data.get("special_tag"), effect_duration=u_data.get("effect_duration", 2), 
            apply_effect_first=u_data.get("apply_effect_first", False), 
            is_split_damage=u_data.get("is_split_damage", False), target_count=u_data.get("target_count", 0),
            apply_effect_per_hit=u_data.get("apply_effect_per_hit", False)
        )
        
        if p_data:
            self.passive = GamePassive(
                p_data["name"], p_data["trigger"], p_data.get("chance", 100), p_data.get("effect", "none"),
                max_triggers=p_data.get("max_triggers_per_turn", 999), special_tag=p_data.get("special_tag"),
                effect_duration=p_data.get("effect_duration", 2), max_triggers_per_battle=p_data.get("max_triggers_per_battle", 999),
                cd=p_data.get("cd", 0)
            )
            self.passive_cd = 0
        else:
            self.passive = None
        
        self.passive_triggers_this_turn = 0
        self.passive_triggers_total = 0

    def get_current_atk(self):
        mod = 1.0
        if "增攻" in self.effects: mod += 0.25
        if "降攻" in self.effects: mod -= 0.35
        if "狂暴" in self.effects: mod += 0.40
        if "保護" in self.effects: mod -= 0.60
        if "醒目" in self.effects: mod += 0.10
        if "音樂" in self.effects: mod -= (0.03 * getattr(self, "effect_stacks", {}).get("音樂", 1))
        if "降雨" in self.effects and getattr(self, "passive", None) and getattr(self.passive, "special_tag", None) == "yuehong_passive": mod += 0.20
        return int(self.atk * max(0.1, mod))

    def get_current_def(self):
        mod = 1.0
        if "增防" in self.effects: mod += 0.25
        if "降防" in self.effects: mod -= 0.40
        if "狂暴" in self.effects: mod -= 0.60
        if "保護" in self.effects: mod += 0.40
        if "灼傷" in self.effects: mod -= 0.10
        if "冰凍" in self.effects: mod -= 0.10
        if "音樂" in self.effects: mod -= (0.03 * getattr(self, "effect_stacks", {}).get("音樂", 1))
        if "降雨" in self.effects and getattr(self, "passive", None) and getattr(self.passive, "special_tag", None) == "yuehong_passive": mod -= 0.50
        return int(self.defense * max(0.1, mod))

    def apply_heal(self, amount, log_lines, source_char=None):
        if "禁療" in self.effects and "詛咒" not in self.effects:
            return 0
            
        if "詛咒" in self.effects:
            actual_dmg, _ = self.take_damage(None, amount, is_true_damage=True, is_effect_damage=True)
            log_lines.append(f" 💀 **{self.name}** 受到 [詛咒] 影響，治療逆轉為 `{actual_dmg}` 點真實傷害")
            return -actual_dmg
            
        actual_heal = min(self.max_hp - self.hp, amount)
        if actual_heal > 0:
            self.hp += actual_heal
            if source_char: source_char.stats_healing_done += actual_heal
            return actual_heal
        return 0

    def add_effect(self, effect_name, duration, log_lines, value=0, silent=False):
        """附加狀態 (支援靜音模式，但例外抵擋必定會顯示)"""
        
        if getattr(self, "is_immune_to_all", False):
            immune_msg = f" ☕ **{self.name}** 的 [咖啡精神] 讓她免疫了狀態異常！"
            if immune_msg not in log_lines:
                log_lines.append(immune_msg)
            return
        
        if effect_name in DEBUFF_LIST and "免疫" in self.effects:
            log_lines.append(f" 🛡️ **{self.name}** 處於 [免疫] 狀態，抵擋了 [{effect_name}]")
            return
            
        if "醒目" in self.effects and effect_name in ["暈眩", "昏迷", "魅惑"]:
            log_lines.append(f" 👁️ **{self.name}** 處於 [醒目] 狀態，無視了 [{effect_name}]")
            return
            
        if "抗寒" in self.effects and effect_name == "冰霜":
            log_lines.append(f" 🧣 **{self.name}** 的 [抗寒] 抵禦了 [冰霜]")
            return
            
        if effect_name == "壓制" and getattr(self, "passive", None) and getattr(self.passive, "special_tag", None) == "xinyue_passive":
            log_lines.append(f" ✨ **{self.name}** 觸發 [星月加護]，免疫了 [壓制]")
            return
        
        if effect_name == "中毒" and getattr(self, "passive", None) and getattr(self.passive, "effect", None) == "免疫中毒":
            log_lines.append(f" 🌿 **{self.name}** 觸發被動，免疫了 [中毒]")
            return
        
        if effect_name == "魅惑" and getattr(self, "passive", None) and getattr(self.passive, "effect", None) == "免疫魅惑":
            log_lines.append(f" 🚫 **{self.name}** 觸發被動，免疫了 [魅惑]")
            return
            
        if effect_name in BUFF_LIST and "壓制" in self.effects:
            log_lines.append(f" ⛓️ **{self.name}** 處於 [壓制] 狀態，無法獲得 [{effect_name}]")
            return

        if effect_name == "護盾":
            self.shield_hp += value
            if not silent:
                log_lines.append(f" 🔰 **{self.name}** 獲得了 `{value}` 點 [護盾]")
        else:
            if effect_name in ["免傷", "受損", "灼燒", "冰霜","音樂"]:
                self.effects[effect_name] = 999 
                current_stacks = self.effect_stacks.get(effect_name, 0)
                if current_stacks < 5:
                    self.effect_stacks[effect_name] = current_stacks + 1
                
                stacks = self.effect_stacks[effect_name]
                if not silent:
                    icon = "🎵" if effect_name == "音樂" else "🏷️"
                    log_lines.append(f" {icon} **{self.name}** 被附加了 [{effect_name}印記] (目前 {stacks} 層)")
            else:
                self.effects[effect_name] = max(self.effects.get(effect_name, 0), duration)
                self.effect_stacks[effect_name] = 1
                if not silent:
                    log_lines.append(f" 🏷️ **{self.name}** 被附加了 [{effect_name}]")
                
            self.newly_applied_this_turn.add(effect_name)
            
        if effect_name in ["降攻", "降防", "中毒"] and getattr(self, "passive", None) and getattr(self.passive, "special_tag", None) == "jiyu_passive":
            if getattr(self, "passive_cd", 0) <= 0:
                self.passive_cd = getattr(self.passive, "cd", 1) # 進入 CD
                
                # 對應的轉換字典
                counter_buff = {"降攻": "增攻", "降防": "增防", "中毒": "治癒"}[effect_name]
                
                self.add_effect(counter_buff, 1, log_lines)
                log_lines.append(f" 🍃 **{self.name}** 觸發 [順風庇護]，獲得 [{counter_buff}]")

    def take_damage(self, attacker, base_damage, is_true_damage=False, is_effect_damage=False):
        passive_logs = []
        
        # 1. 防禦計算
        if is_true_damage or is_effect_damage:
            actual_damage = base_damage
        else:
            curr_def = self.get_current_def()
            actual_damage = max(1, base_damage if base_damage + curr_def == 0 else int(base_damage * (base_damage / (base_damage + curr_def))))

        # 👉 新增：無敵狀態絕對防禦直接把傷害歸 0
        if "無敵" in self.effects:
            actual_damage = 0
            passive_logs.append(f" ✨ **{self.name}** 處於 [無敵] 狀態，免疫了所有傷害")

        # 1.5 狀態增減傷 (易傷 / 免傷 / 受損 / 破甲 / 陽瑜被動減傷 / 梓旭特攻)
        if "易傷" in self.effects: actual_damage = int(actual_damage * 1.25)
        if "受損" in self.effect_stacks: actual_damage = int(actual_damage * (1 + 0.03 * self.effect_stacks["受損"]))
        if "免傷" in self.effect_stacks: actual_damage = int(actual_damage * (1 - 0.03 * self.effect_stacks["免傷"]))
        if attacker and "破甲" in attacker.effects and self.shield_hp > 0: actual_damage = int(actual_damage * 1.5)
        if "嘲諷" in self.effects and getattr(self, "passive", None) and getattr(self.passive, "special_tag", None) == "yangyu_passive": actual_damage = int(actual_damage * 0.5)
        if "昏迷" in self.effects and attacker and getattr(attacker, "passive", None) and getattr(attacker.passive, "special_tag", None) == "zixu_passive": actual_damage = int(actual_damage * 1.5)

        total_dmg_this_hit = 0
        ignores_shield = attacker and getattr(attacker, "passive", None) and getattr(attacker.passive, "special_tag", None) == "yuming_passive"

        # 2. 護盾抵擋
        if not is_effect_damage and self.shield_hp > 0:
            if ignores_shield:
                total_dmg_this_hit = actual_damage
            elif self.shield_hp >= actual_damage:
                self.shield_hp -= actual_damage
                total_dmg_this_hit = actual_damage
                actual_damage = 0
                passive_logs.append(f"   🛡️ 護盾吸收了 `{total_dmg_this_hit}` 點傷害")
            else:
                absorbed = self.shield_hp
                actual_damage -= self.shield_hp
                self.shield_hp = 0
                if getattr(self, "passive", None) and getattr(self.passive, "special_tag", None) == "yechen_passive":
                    self.add_effect("免傷", 999, passive_logs)
                total_dmg_this_hit = absorbed + actual_damage
                passive_logs.append(f"   💔 護盾吸收 `{absorbed}` 點傷害後破裂了")
        else:
            total_dmg_this_hit = actual_damage

        # 紀錄數據
        self.stats_dmg_taken += total_dmg_this_hit
        if attacker: attacker.stats_dmg_dealt += total_dmg_this_hit
        if not is_effect_damage and "降雨" in self.effects:
            self.rain_hits = getattr(self, "rain_hits", 0) + 1

        if actual_damage == 0:
            return 0, passive_logs

        # 3. 昏迷受擊喚醒
        if not is_effect_damage and "昏迷" in self.effects and actual_damage > 0:
            if random.randint(1, 100) <= 25:
                del self.effects["昏迷"]
                passive_logs.append(f" 💢 **{self.name}** 受到痛擊，從 [昏迷] 中醒來了")

        # 4. 扣血與全新【不屈】機制
        if self.hp > 1 and (self.hp - actual_damage <= 0) and "不屈" in self.effects:
            self.hp = 1
            self.add_effect("無敵", 1, passive_logs)
            passive_logs.append(f" ❤️‍🔥 **{self.name}** 觸發 [不屈]，生命值鎖定為 1 點並獲得 [無敵]")
        else:
            self.hp = max(0, self.hp - actual_damage)

        # 5. 受擊被動 (含瀕死判定)
        is_revive_passive = getattr(self, "passive", None) and getattr(self.passive, "special_tag", None) == "lingyu_passive"
        if not is_effect_damage and "封印" not in self.effects:
            if self.hp > 0 or is_revive_passive:
                self_passive = getattr(self, "passive", None)
                if self_passive and getattr(self_passive, "trigger", None) == "on_hit":
                    if getattr(self, "passive_cd", 0) <= 0 and getattr(self, "passive_triggers_total", 0) < getattr(self_passive, "max_triggers_per_battle", 999):
                        can_trigger = True
                        if getattr(self_passive, "special_tag", None):
                            can_trigger = check_special_passive(self_passive.special_tag, self, attacker)
                        
                        if can_trigger and random.randint(1, 100) <= getattr(self_passive, "chance", 100):
                            self.passive_triggers_total = getattr(self, "passive_triggers_total", 0) + 1
                            self.passive_cd = getattr(self_passive, "cd", 0) 
                            
                            if self_passive.special_tag == "lingyu_passive":
                                heal_amt = int(self.max_hp * 0.5)
                                actual_heal = self.apply_heal(heal_amt, passive_logs, self)
                                if actual_heal > 0: 
                                    passive_logs.append(f" 🌸 **{self.name}** 生命值低於 10%，觸發被動恢復 `{actual_heal}` 點生命")
                                self.add_effect("免疫", 2, passive_logs)
                            elif self_passive.special_tag == "yemo_passive":
                                if attacker:
                                    attacker.add_effect("壓制", 1, passive_logs)
                                    passive_logs.append(f" 🍁 **{self.name}** 觸發被動漫天落葉將 **{attacker.name}** 給 [壓制] 了")    
                            elif self_passive.special_tag == "mingyu_passive":
                                self.add_effect("增防", 1, passive_logs)
                                passive_logs.append(f" 🎋 **{self.name}** 觸發被動，獲得 [增防]")
                            elif self_passive.special_tag == "yinyu_passive":
                                self.add_effect("增攻", 1, passive_logs)
                                passive_logs.append(f" 🐧 **{self.name}** 觸發被動，獲得 [增攻]")
                            else:
                                if getattr(self_passive, "effect", None) in DEBUFF_LIST:
                                    if attacker: attacker.add_effect(self_passive.effect, self_passive.effect_duration, passive_logs)
                                    passive_logs.append(f" └ 🛡️ **{self.name}** 觸發被動，使攻擊者受到 [{self_passive.effect}]")
                                elif getattr(self_passive, "effect", None) != "none":
                                    self.add_effect(self_passive.effect, self_passive.effect_duration, passive_logs)
        
        # 6. 攻擊者造成傷害時的被動 (on_deal_damage)
        attacker_passive = getattr(attacker, "passive", None)
        if actual_damage > 0 and attacker and attacker_passive and getattr(attacker_passive, "trigger", None) == "on_deal_damage" and not is_effect_damage:
            if attacker.hp > 0 and "封印" not in attacker.effects:
                if getattr(attacker, "passive_cd", 0) <= 0 and getattr(attacker, "passive_triggers_total", 0) < getattr(attacker_passive, "max_triggers_per_battle", 999):
                    if random.randint(1, 100) <= getattr(attacker_passive, "chance", 100):
                        attacker.passive_triggers_total = getattr(attacker, "passive_triggers_total", 0) + 1
                        attacker.passive_cd = getattr(attacker_passive, "cd", 0)
                        
                        if attacker_passive.special_tag == "lingyun_passive":
                            debuffs = ["降攻", "降防", "中毒", "禁療", "封印", "壓制", "易傷", "灼傷", "鎖定"]
                            chosen = random.choice(debuffs)
                            self.add_effect(chosen, attacker_passive.effect_duration, passive_logs)
                        elif attacker_passive.special_tag == "yunya_passive":
                            if attacker.hp <= int(attacker.max_hp * 0.5):
                                heal_amt = int(actual_damage * 0.5)
                                actual_heal = attacker.apply_heal(heal_amt, passive_logs, attacker)
                                if actual_heal > 0:
                                    passive_logs.append(f" 🦇 **{attacker.name}** 觸發 [青春活力]，吸取了 `{actual_heal}` 點生命")

        # 7. 反傷機制 (不會反死對手)
        if "反傷" in self.effects and attacker and not is_effect_damage and total_dmg_this_hit > 0:
            reflect_amt = int(total_dmg_this_hit * 0.35)
            reflect_amt = min(reflect_amt, attacker.hp - 1)
            if reflect_amt > 0:
                attacker.hp -= reflect_amt
                passive_logs.append(f" 🪞 **{self.name}** 的 [反傷] 將 `{reflect_amt}` 點傷害彈回給了 **{attacker.name}**")

        # 8. 死亡清理
        if self.hp <= 0:
            self.effects.clear()
            self.effect_stacks.clear()
            self.shield_hp = 0
            
        return actual_damage, passive_logs

    def tick_turn_effects(self, log_lines):
        """【個人回合結束】結算數值與控制狀態"""
        if self.hp <= 0: return
        expired = []
        for k in list(self.effects.keys()):
            if k in ["中毒", "治癒", "抗寒", "灼傷", "灼燒"]:
                continue 
                
            if self.effects[k] != 999:
                if k in getattr(self, "newly_applied_this_turn", set()):
                    continue
                    
                self.effects[k] -= 1
                if self.effects[k] <= 0:
                    expired.append(k)
                    del self.effects[k]
                    if k in self.effect_stacks: del self.effect_stacks[k]
                    
        self.passive_triggers_this_turn = 0
        self.newly_applied_this_turn.clear()

    def tick_round_effects(self, log_lines):
        """【全局回合結束】結算生命值改變狀態 (支援詛咒/灼傷/抗寒/抵銷機制)"""
        if self.hp <= 0: return

        has_poison = "中毒" in self.effects
        has_hot = "治癒" in self.effects

        # 中毒與治癒抵銷
        if has_poison and has_hot and "詛咒" not in self.effects and "禁療" not in self.effects:
            log_lines.append(f" ⚖️ **{self.name}** 身上的 [中毒] 與 [治癒] 互相抵銷了")
            self._tick_specific_effect("中毒", log_lines)
            self._tick_specific_effect("治癒", log_lines)
        else:
            if has_poison:
                dmg = int(self.max_hp * 0.05)
                actual_dmg, _ = self.take_damage(None, dmg, is_effect_damage=True, is_true_damage=True)
                log_lines.append(f" 🤢 **{self.name}** 受到中毒傷害 `{actual_dmg}` 點")
                self._tick_specific_effect("中毒", log_lines)
                
            if has_hot:
                heal = int(self.max_hp * 0.05)
                actual_heal = self.apply_heal(heal, log_lines, self)
                if actual_heal > 0:
                    log_lines.append(f" 💚 **{self.name}** 受到治癒，恢復 `{actual_heal}` 點生命")
                self._tick_specific_effect("治癒", log_lines)

        has_cold = "抗寒" in self.effects
        has_burn = "灼傷" in self.effects

        if has_cold and has_burn:
            log_lines.append(f" ⚖️ **{self.name}** 身上的 [抗寒] 與 [灼傷] 冰火相剋，互相抵銷了")
            self._tick_specific_effect("抗寒", log_lines)
            self._tick_specific_effect("灼傷", log_lines)
        else:
            if has_cold:
                heal = int(self.max_hp * 0.03)
                actual_heal = self.apply_heal(heal, log_lines, self)
                if actual_heal > 0:
                    log_lines.append(f" 🧣 **{self.name}** 受到 [抗寒] 庇護，恢復 `{actual_heal}` 點生命")
                self._tick_specific_effect("抗寒", log_lines)

            if has_burn:
                dmg = int(self.max_hp * 0.03)
                actual_dmg, _ = self.take_damage(None, dmg, is_effect_damage=True, is_true_damage=True)
                log_lines.append(f" 🔥 **{self.name}** 受到 [灼傷] 影響，扣除 `{actual_dmg}` 點生命")
                self._tick_specific_effect("灼傷", log_lines)
            
        if "灼燒" in self.effect_stacks:
            stacks = self.effect_stacks["灼燒"]
            dmg = int(self.max_hp * 0.03 * stacks)
            actual_dmg, _ = self.take_damage(None, dmg, is_effect_damage=True, is_true_damage=True)
            log_lines.append(f" 🔥 **{self.name}** 的 [灼燒] 印記發作({stacks}層)，扣除 `{actual_dmg}` 點生命")

        if self.hp <= 0:
            log_lines.append(f" 💀 **{self.name}** 倒下了")

    def _tick_specific_effect(self, effect_name, log_lines):
        """內部工具：專門扣除單一狀態的壽命"""
        if effect_name in self.effects and self.effects[effect_name] != 999:
            self.effects[effect_name] -= 1
            if self.effects[effect_name] <= 0:
                del self.effects[effect_name]
                if effect_name in self.effect_stacks: del self.effect_stacks[effect_name]

    def tick_cd(self):
        if self.small_skill.current_cd > 0: self.small_skill.current_cd -= 1
        if self.ult_skill.current_cd > 0: self.ult_skill.current_cd -= 1
        if getattr(self, "passive_cd", 0) > 0: self.passive_cd -= 1

    def get_action_status(self):
        if "暈眩" in self.effects: return "skip", "💫 處於 [暈眩] 狀態，無法行動"
        if "昏迷" in self.effects: return "skip", "💤 處於 [昏迷] 狀態，無法行動"
        if "冰凍" in self.effects: return "skip", "❄️ 處於 [冰凍] 狀態，無法行動"
        if "魅惑" in self.effects: return "charm", "💞 受到 [魅惑]，將攻擊自己"
        if "沈默" in self.effects: return "silence", "🤐 處於 [沈默] 狀態，只能使用普攻"
        return "normal", ""

    def choose_action(self):
        if self.ult_skill.current_cd == 0: return self.ult_skill
        if self.small_skill.current_cd == 0: return self.small_skill
        return self.normal_skill
    
def process_rain_effects(team, enemies, log_lines):
    """【全局回合結算】處理降雨與其他需要全隊判定的機制"""
    from engine import DEBUFF_LIST
    
    # 👉 郁荷被動特判：天台高處 (維持不變)
    alive_members = [c for c in team if c.hp > 0]
    if len(alive_members) == 1:
        last_man = alive_members[0]
        if getattr(last_man, "passive", None) and getattr(last_man.passive, "special_tag", None) == "yuhe_passive":
            if last_man.effects.get("反傷", 0) != 999:
                last_man.effects["反傷"] = 999
                log_lines.append(f" 🏙️ **{last_man.name}** 觸發 [天台高處]作為最後的壁壘，獲得永久 [反傷]")
    
    rain_members = [c for c in team if c.hp > 0 and "降雨" in c.effects]
    total_rain = sum(getattr(c, "rain_hits", 0) for c in team)
    
    if not rain_members or total_rain == 0:
        # 場上沒人有降雨 或 沒人受擊，清空計數並結束
        for c in team: 
            if hasattr(c, "rain_hits"): c.rain_hits = 0
        return

    # 🌟 核心更新：結算基準判斷 (優先選擇施放者)
    def is_rain_caster(c):
        # 透過檢查技能 tag 判斷該角色是否為「產雨角色」(如月虹、馨喬)
        small_tag = getattr(c.small_skill, "special_tag", "") if hasattr(c, "small_skill") and c.small_skill else ""
        ult_tag = getattr(c.ult_skill, "special_tag", "") if hasattr(c, "ult_skill") and c.ult_skill else ""
        return "yuehong" in small_tag or "yuehong" in ult_tag or "xinqiao" in small_tag or "xinqiao" in ult_tag

    # 將擁有降雨的成員重新排序：產雨角色優先排在最前面，其餘照原本攻擊順位
    sorted_rain_members = sorted(rain_members, key=lambda c: not is_rain_caster(c))
    primary_caster = sorted_rain_members[0]
    
    atk_val = primary_caster.atk

    log_lines.append(f" 🌧️ 【降雨結算】我方累積了 `{total_rain}` 點降雨值(由 **{primary_caster.name}** 結算)")

    # 發動對應能力的傷害與恢復
    dmg_mult = 0.0
    heal_mult = 0.0
    dispel_debuff = False

    if 1 <= total_rain <= 5:
        dmg_mult = 0.25
    elif 6 <= total_rain <= 10:
        dmg_mult, heal_mult = 0.5, 0.25
    elif 11 <= total_rain <= 15:
        dmg_mult, heal_mult = 0.75, 0.5
    elif total_rain > 15:
        dmg_mult, heal_mult = 1.0, 1.0
        dispel_debuff = True

    # 1. 造成全體傷害
    total_rain_dmg = 0
    p_logs_acc = []
    for e in enemies:
        if e.hp > 0:
            dmg, p_logs = e.take_damage(attacker=primary_caster, base_damage=int(atk_val * dmg_mult))
            total_rain_dmg += dmg
            p_logs_acc.extend(p_logs)
            
    if total_rain_dmg > 0:
        log_lines.append(f"  🌊 水流沖擊對 **全體敵人** 總計造成了 `{total_rain_dmg}` 點傷害！")
        log_lines.extend(p_logs_acc)
            
    # 2. 恢復全隊生命
    if heal_mult > 0:
        heal_amt = int(atk_val * heal_mult)
        total_rain_heal = 0
        dummy_logs = []
        
        for a in team:
            if a.hp > 0:
                actual_heal = a.apply_heal(heal_amt, dummy_logs, primary_caster)
                total_rain_heal += actual_heal
                
        if total_rain_heal > 0:
            log_lines.append(f"  💚 雨水滋潤了大家，全隊每人恢復了 `{heal_amt}` 點生命！")
                    
    # 3. 驅散負面狀態
    if dispel_debuff:
        for a in team:
            if a.hp > 0:
                debuffs = [k for k in a.effects.keys() if k in DEBUFF_LIST]
                if debuffs:
                    removed = random.choice(debuffs)
                    del a.effects[removed]
                    if removed in getattr(a, "effect_stacks", {}): del a.effect_stacks[removed]
                    log_lines.append(f"  💨 **{a.name}** 的 [{removed}] 被雨水淨化了")

    # 結算完畢，重置全隊點數
    for c in team:
        if hasattr(c, "rain_hits"): c.rain_hits = 0
