import math
import os
import re
import json
import logging
from datetime import datetime

# =====================================================================
# НАСТРОЙКА СИСТЕМНОГО ЛОГИРОВАНИЯ
# =====================================================================
log_filename = f"tacheometry_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(log_filename, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(console_handler)

def log_and_print(message):
    """Дублирует важные сообщения и ведомости одновременно в консоль и в файл лога"""
    logger.info(message)

def clear_screen():
    """Очищает экран терминала в зависимости от текущей операционной системы"""
    os.system('cls' if os.name == 'nt' else 'clear')


# =====================================================================
# СЛОВАРИ ДЛЯ КОНВЕРТАЦИИ И ИНИЦИАЛИЗАЦИЯ ДАННЫХ
# =====================================================================
ARABIC_TO_ROMAN = {
    1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 
    6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X",
    11: "XI", 12: "XII", 13: "XIII", 14: "XIV", 15: "XV"
}
ROMAN_TO_ARABIC = {v: k for k, v in ARABIC_TO_ROMAN.items()}

CURRENT_PROJECT_FILE = "survey_state.json"

state = {
    "coord_digits": 2,
    "height_digits": 2,
    "catalog_points": {},
    "instrument": "2Т30",
    "measurements": [],
    "piket_global_counter": 1,
    "tacheometry_data": {}
}

def save_state():
    """Сохраняет все текущие изменения сессии в выбранный JSON файл проекта"""
    with open(CURRENT_PROJECT_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=4)

def load_state():
    """Загружает сохраненную структуру данных из выбранного JSON файла"""
    global state
    if os.path.exists(CURRENT_PROJECT_FILE):
        try:
            with open(CURRENT_PROJECT_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
            log_and_print(f"[СИСТЕМА] База объекта '{CURRENT_PROJECT_FILE.replace('.json', '')}' успешно подгружена!")
        except Exception as e:
            log_and_print(f"[СИСТЕМА] Не удалось прочитать файл проекта: {e}. Создана пустая сессия.")


# =====================================================================
# МАТЕМАТИЧЕСКИЕ И ВСПOМОГАТЕЛЬНЫЕ ГЕОДЕЗИЧЕСКИЕ ФУНКЦИИ
# =====================================================================
def parse_angle(prompt, instrument, default_val=None):
    """
    Принимает угловые отсчеты из консоли (ГГ ММ СС), проверяет их синтаксис
    и автоматически округляет секунды/минуты под точность указанного прибора.
    """
    match = re.search(r'T(\d+)', instrument.upper().replace('Т', 'T'))
    accuracy_class = int(match.group(1)) if match else 30

    while True:
        try:
            suffix = f" (Enter: {decimal_to_dms(default_val)})" if default_val is not None else ""
            print(f"[{instrument}] {prompt}{suffix}")
            raw_input = input("Введите через пробел (Градусы Минуты Секунды) или 'б' для отмены: ").strip()
            
            if raw_input.lower() in ['б', 'назад', 'cancel']:
                clear_screen()
                return None
            if not raw_input:
                if default_val is not None:
                    return default_val
                print("[ОШИБКА] Значение угла не может быть пустым!")
                continue
            
            sign = -1 if raw_input.startswith('-') else 1
            clean_input = raw_input.replace('-', '').replace('+', '').split()

            deg = float(clean_input[0])
            minutes = float(clean_input[1]) if len(clean_input) > 1 else 0.0
            seconds = float(clean_input[2]) if len(clean_input) > 2 else 0.0

            if accuracy_class >= 30: 
                if seconds != 0:
                    minutes += seconds / 60.0
                    seconds = 0.0
                minutes = round(minutes * 2) / 2
            elif accuracy_class >= 5:
                seconds = round(seconds)
            elif accuracy_class < 5:
                seconds = round(seconds, 1)
            
            return sign * (deg + minutes / 60.0 + seconds / 3600.0)
        except (ValueError, IndexError):
            print("Ошибка ввода! Схема: Градусы [пробел] Минуты [пробел] Секунды. Повторите.")

def decimal_to_dms(decimal_deg):
    """Конвертирует десятичные градусы в стандартную геодезическую строку ГГ°ММ'СС\""""
    if decimal_deg is None: 
        return "N/A"
    sign = "-" if decimal_deg < 0 else "+"
    abs_deg = abs(decimal_deg)
    degrees = int(abs_deg)
    minutes_float = (abs_deg - degrees) * 60
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60)
    
    if seconds == 60:
        minutes += 1
        seconds = 0
    if minutes == 60:
        degrees += 1
        minutes = 0
    return f"{sign}{degrees}°{minutes:02d}'{seconds:02d}\""


# =====================================================================
# ИНТЕРФЕЙСНЫЙ БЛОК: КАТАЛОГ ОПОРНЫХ ТОЧЕК
# =====================================================================
def menu_catalog_points():
    """Управление каталогом координат и высот твердых геодезических пунктов"""
    while True:
        clear_screen()
        log_and_print("\n=== КАТАЛОГ ОПОРНЫХ ТОЧЕК ===")
        print(f"Текущие настройки округления: X,Y = {state['coord_digits']} зн., H = {state['height_digits']} зн.")
        print("\nТочки в базе:")
        if not state["catalog_points"]:
            print("  [Каталог пуст]")
        for idx_str, data in state["catalog_points"].items():
            h_val = f"{data['h']:.{state['height_digits']}f} м" if data['h'] is not None else "Неизвестно"
            print(f"  Точка {data['roman']} (№{idx_str}): X={data['x']:.{state['coord_digits']}f} м, Y={data['y']:.{state['coord_digits']}f} м, H={h_val}")
            
        print("\nДействия:")
        print("  1 - Добавить / Изменить координаты точки")
        print("  2 - Настроить точность округления")
        print("  0 - Вернуться в главное меню (или нажмите Enter)")
        
        choice = input("Выбор: ").strip()
        
        if not choice or choice == '0':
            clear_screen()
            break
            
        elif choice == '1':
            inp_num = input("\nВведите АРАБСКИЙ номер точки (например: 1, 2, 3): ").strip()
            if not inp_num:
                print("[ОШИБКА] Номер точки не может быть пустым!")
                input("Нажмите Enter...")
                continue
                
            try:
                idx = int(inp_num)
                idx_str = str(idx)
                r_num = ARABIC_TO_ROMAN.get(idx, f"№{idx}")
                
                old_data = state["catalog_points"].get(idx_str, {})
                print(f"--- Ввод данных для точки {r_num} ---")
                
                # Координата X
                x_prompt = f"Координата X (м) (сейчас: {old_data['x']}): " if 'x' in old_data else "Координата X (м): "
                x_inp = input(x_prompt).strip()
                if not x_inp and 'x' not in old_data:
                    print("[ОШИБКА] Координата X обязательна для новой точки!")
                    input("Нажмите Enter...")
                    continue
                x = round(float(x_inp), state["coord_digits"]) if x_inp else old_data['x']
                
                # Координата Y
                y_prompt = f"Координата Y (м) (сейчас: {old_data['y']}): " if 'y' in old_data else "Координата Y (м): "
                y_inp = input(y_prompt).strip()
                if not y_inp and 'y' not in old_data:
                    print("[ОШИБКА] Координата Y обязательна для новой точки!")
                    input("Нажмите Enter...")
                    continue
                y = round(float(y_inp), state["coord_digits"]) if y_inp else old_data['y']
                
                # Высота H
                h_old_str = f"{old_data['h']} м" if old_data.get('h') is not None else "неизвестна"
                h_prompt = f"Высота H (м) [сейчас: {h_old_str}]: " if old_data else "Высота H (м) [Enter если неизвестна]: "
                h_inp = input(h_prompt).strip()
                
                if h_inp:
                    h = round(float(h_inp), state["height_digits"])
                else:
                    h = old_data.get('h') if old_data else None
                
                state["catalog_points"][idx_str] = {"roman": r_num, "x": x, "y": y, "h": h}
                save_state()
                log_and_print(f"[Успешно] Данные точки {r_num} зафиксированы в базе!")
                input("Нажмите Enter для продолжения...")
            except ValueError:
                print("Ошибка! Вводите только числовые значения. Данные проигнорированы.")
                input("Нажмите Enter...")
                
        elif choice == '2':
            try:
                c_dig = input(f"Округление X, Y в метрах (сейчас {state['coord_digits']}, Enter чтобы оставить): ").strip()
                state["coord_digits"] = int(c_dig) if c_dig else state["coord_digits"]
                
                h_dig = input(f"Округление H в метрах (сейчас {state['height_digits']}, Enter чтобы оставить): ").strip()
                state["height_digits"] = int(h_dig) if h_dig else state["height_digits"]
                
                save_state()
                print("Параметры округления успешно обновлены.")
            except ValueError:
                print("Ошибка ввода. Параметры оставлены без изменений.")
                input("Нажмите Enter...")
        
        else:
            # Если ввели несуществующий пункт — чистим экран и заходим на этот уровень заново
            clear_screen()


# =====================================================================
# ИНТЕРФЕЙСНЫЙ БЛОК: ВЫСОТНЫЙ ГЕОДЕЗИЧЕСКИЙ ХОД
# =====================================================================
def menu_height_traverse():
    """Журнал геометрического/тригонометрического нивелирования по станциям"""
    while True:
        clear_screen()
        print(f"\n=== ЖУРНАЛ ИЗМЕРЕНИЙ ВЫСОТНОГО ХОДА | ПРИБОР: {state['instrument']} ===")
        print("\nСписок текущих связующих звеньев:")
        if not state["measurements"]:
            print("  [Журнал измерений пуст]")
        for i, m in enumerate(state["measurements"]):
            f_rom = state["catalog_points"].get(str(m['from']), {}).get('roman', f"№{m['from']}")
            t_rom = state["catalog_points"].get(str(m['to']), {}).get('roman', f"№{m['to']}")
            print(f"  [{i+1}] {f_rom} -> {t_rom} | D'={m['d_prime']} м, h={m['h_diff']} м")
            
        print("\nДействия:")
        print("  1 - Начать / Продолжить ввод станций")
        print("  2 - Удалить ошибочную запись перегона")
        print("  3 - Выполнить расчет невязку и уравнивание высот")
        print("  0 - Вернуться в главное меню (или нажмите Enter)")
        
        choice = input("Выбор: ").strip()
        
        if not choice or choice == '0':
            clear_screen()
            break
            
        elif choice == '1':
            if len(state["catalog_points"]) < 2:
                print("Ошибка: Для прокладывания хода внесите минимум 2 точки в каталог!")
                input("Нажмите Enter...")
                continue

            clear_screen()    
            print("\n=== ЗАПУЩЕН РЕЖИМ ВВОДА ЖУРНАЛА ===")
            
            while True:
                points_list = [f"{k} ({v['roman']})" for k, v in state['catalog_points'].items()]
                print("(Для выхода из цикла просто нажмите Enter на запросе точки станции)\n")
                print(f"Доступные точки: {', '.join(points_list)}")
                
                f_inp = input("Точка СТАНЦИИ (откуда смотрим): ").strip()
                if not f_inp:
                    break
                    
                t_inp = input("Точка НАВЕДЕНИЯ (куда смотрим): ").strip()
                if not t_inp:
                    print("[ОШИБКА] Ввод прерван (не указана смежная точка).")
                    input("Нажмите Enter...")
                    break
                    
                try:
                    f = int(f_inp)
                    t = int(t_inp)
                    
                    if str(f) not in state["catalog_points"] or str(t) not in state["catalog_points"]:
                        clear_screen()
                        print("Ошибка: Одной из точек нет в каталоге опорной сети! Повторите ввод.")
                        continue
                    
                    old_m = {}
                    for m in state["measurements"]:
                        if m["from"] == f and m["to"] == t:
                            old_m = m
                            break
                    
                    kl = parse_angle("Отсчет по КЛ:", state["instrument"], old_m.get("kl"))
                    if kl is None: continue
                    kp = parse_angle("Отсчет по КП:", state["instrument"], old_m.get("kp"))
                    if kp is None: continue
                    
                    d_p_prompt = f"Дальномерное расстояние D' (м) (сейчас: {old_m['d_prime']}): " if 'd_prime' in old_m else "Дальномерное расстояние D' (м): "
                    d_p_inp = input(d_p_prompt).strip()
                    if not d_p_inp and 'd_prime' not in old_m:
                        print("[ОШИБКА] Расстояние не может быть пустым!")
                        continue
                    d_prime = float(d_p_inp) if d_p_inp else old_m['d_prime']
                    
                    i_prompt = f"Высота оси вращения трубы прибора i (м) (сейчас: {old_m['i']}): " if 'i' in old_m else "Высота оси вращения трубы прибора i (м): "
                    i_inp = input(i_prompt).strip()
                    if not i_inp and 'i' not in old_m:
                        print("[ОШИБКА] Высота прибора не может быть пустой!")
                        continue
                    inst_h = float(i_inp) if i_inp else old_m['i']
                    
                    v_prompt = f"Высота цели визирования v (м) (сейчас: {old_m['v']}): " if 'v' in old_m else "Высота цели визирования v (м): "
                    v_inp = input(v_prompt).strip()
                    if not v_inp and 'v' not in old_m:
                        print("[ОШИБКА] Высота цели не может быть пустой!")
                        continue
                    vis_h = float(v_inp) if v_inp else old_m['v']
                    
                    clear_screen()

                    mo = (kl + kp) / 2.0
                    nu = kl - mo
                    h_prime = round(d_prime * 0.5 * math.sin(2 * math.radians(nu)), 2)
                    h_diff = round(h_prime + inst_h - vis_h, 2)
                    
                    new_measurement = {
                        "from": f, "to": t, "kl": kl, "kp": kp, "mo": mo, "nu": nu,
                        "d_prime": d_prime, "i": inst_h, "v": vis_h, "h_prime": h_prime, "h_diff": h_diff
                    }

                    existing_idx = None
                    for idx, item in enumerate(state["measurements"]):
                        if item["from"] == f and item["to"] == t:
                            existing_idx = idx
                            break

                    if existing_idx is not None:
                        state["measurements"][existing_idx] = new_measurement
                        log_msg = f"   [ОБНОВЛЕНО] Данные для перегона {state['catalog_points'][str(f)]['roman']} -> {state['catalog_points'][str(t)]['roman']} успешно перезаписаны!"
                    else:
                        state["measurements"].append(new_measurement)
                        log_msg = f"   [ДОБАВЛЕНО] Новый перегон зафиксирован в базе сессии."
                    
                    save_state()
                    
                    f_rom = state["catalog_points"][str(f)]["roman"]
                    t_rom = state["catalog_points"][str(t)]["roman"]
                    print("-" * 60)
                    log_and_print(f"   [Расчет станции] {f_rom} -> {t_rom}:")
                    log_and_print(f"   МО = {decimal_to_dms(mo)} | ν = {decimal_to_dms(nu)} | h' = {h_prime} м | h = {h_diff} м")
                    log_and_print(log_msg)
                    print("-" * 60, "\n")
                    
                except ValueError:
                    print("Ошибка заполнения данных. Измерения текущей станции аннулированы.")
                except KeyError:
                    print("Ошибка сопоставления индексов каталога пунктов.")
                    
        elif choice == '2':
            if not state["measurements"]:
                print("Журнал пуст, удалять нечего.")
                input("Нажмите Enter...")
                continue
            try:
                del_inp = input("Введите номер строки для удаления (с 1): ").strip()
                if not del_inp:
                    continue
                idx = int(del_inp) - 1
                if 0 <= idx < len(state["measurements"]):
                    del state["measurements"][idx]
                    save_state()
                    print("Запись успешно стерта из памяти сессии.")
                else:
                    print("Записи с таким порядковым номером не существует.")
            except ValueError:
                print("Некорректный формат ввода.")
            input("Нажмите Enter...")
                
        elif choice == '3':
            calculate_traverse_results()
            input("\nОбработка хода завершена. Нажмите Enter для возврата...")
            
        else:
            # Несуществующий пункт подменю
            clear_screen()

def calculate_traverse_results():
    """Вычисляет высотные невязки, сверяет с допуском и распределяет поправки пропорционально длинам"""
    if not state["measurements"]:
        print("В журнале отсутствуют данные для выполнения уравнивания.")
        return
        
    legs = {}
    for m in state["measurements"]:
        f, t = m["from"], m["to"]
        pair = (str(min(f, t)), str(max(f, t)))
        if str(pair) not in legs: 
            legs[str(pair)] = {}
        if f < t: 
            legs[str(pair)]["прямо"] = m
        else: 
            legs[str(pair)]["обратно"] = m

    final_legs = []
    sum_s, sum_h_abs = 0.0, 0.0
    
    for pair_str, data in legs.items():
        p_eval = eval(pair_str)
        p_roman = state["catalog_points"][p_eval[0]]["roman"]
        o_roman = state["catalog_points"][p_eval[1]]["roman"]
        
        h_pryamo = data["прямо"]["h_diff"] if "прямо" in data else None
        h_obratno = data["обратно"]["h_diff"] if "обратно" in data else None
        
        if h_pryamo is not None and h_obratno is not None:
            h_sr = round((1 if h_pryamo >= 0 else -1) * ((abs(h_pryamo) + abs(h_obratno)) / 2.0), 2)
            s_dist = data["прямо"]["d_prime"]
        else:
            h_sr = h_pryamo if h_pryamo is not None else -h_obratno
            s_dist = data["прямо"]["d_prime"] if "прямо" in data else data["обратно"]["d_prime"]
            
        sum_s += s_dist
        sum_h_abs += h_sr
        final_legs.append({"pair": p_eval, "name": f"{p_roman} -> {o_roman}", "h_sr": h_sr, "s": s_dist})

    known_heights = {int(k): v["h"] for k, v in state["catalog_points"].items() if v["h"] is not None}
    if len(known_heights) < 2:
        log_and_print("[КРИТИЧЕСКАЯ ОШИБКА] В каталоге должно быть минимум 2 исходных репера с известными H!")
        return
        
    start_idx = min(known_heights.keys())
    end_idx = max(known_heights.keys())
    start_h = known_heights[start_idx]
    end_h = known_heights[end_idx]
    
    fh = round(sum_h_abs - (end_h - start_h), 2)
    n_stations = len(final_legs)
    fh_dop = round(0.04 * sum_s / math.sqrt(n_stations) if n_stations > 0 else 0, 2)
    
    log_and_print(f"\n=== ВЕДОМОСТЬ ВЫЧИСЛЕНИЯ НЕВЯЗКИ ===")
    log_and_print(f"Полученная невязка fh = {fh:+g} м")
    log_and_print(f"Допустимая невязка fh_доп = ±{abs(fh_dop)} м")
    log_and_print(f"Суммарная протяженность хода S = {sum_s} м")
    
    if abs(fh) > abs(fh_dop):
        log_and_print("[ВНИМАНИЕ] Невязка превышает установленный допуск! Требуется перенаблюдение хода.")
    
    total_corr_cm = int(round(-fh * 100))
    for l in final_legs: 
        l["corr"] = 0.0
    
    if total_corr_cm != 0:
        step = 1 if total_corr_cm > 0 else -1
        cm_left = abs(total_corr_cm)
        sorted_legs = sorted(final_legs, key=lambda x: x["s"], reverse=True)
        while cm_left > 0:
            for l in sorted_legs:
                if cm_left == 0: 
                    break
                l["corr"] = round(l["corr"] + step * 0.01, 2)
                cm_left -= 1

    current_h = start_h
    for l in final_legs:
        l["h_испр"] = round(l["h_sr"] + l["corr"], 2)
        next_point = str(l["pair"][1])
        current_h = round(current_h + l["h_испр"], state["height_digits"])
        if state["catalog_points"][next_point]["h"] is None or next_point != str(end_idx):
            state["catalog_points"][next_point]["h"] = current_h
            
    save_state()
    
    log_and_print("\n=== ИТОГОВАЯ УРАВНЕННАЯ ВЕДОМОСТЬ ХОДА ===")
    print(f"{'Перегон хода':<15} | {'S (м)':<8} | {'h_ср (м)':<10} | {'Поправка':<8} | {'h_испр (м)':<10}")
    print("-" * 60)
    for l in final_legs:
        print(f"{l['name']:<15} | {l['s']:<8.1f} | {l['h_sr']:<10.2f} | {l['corr']:<8.2f} | {l['h_испр']:<10.2f}")


# =====================================================================
# ИНТЕРФЕЙСНЫЙ БЛОК: ТАХЕОМЕТРИЧЕСКАЯ СЪЕМКА (ПИКЕТЫ)
# =====================================================================
def menu_tacheometry():
    """Журнал съёмки пикетов подробностей местности с жестких станций"""
    last_i = None
    last_v = None
    
    while True:
        clear_screen()
        log_and_print("\n=== ЖУРНАЛ ТАХЕОМЕТРИЧЕСКОЙ СЪЕМКИ ===")
        print(f"Текущий сквозной номер пикета в сессии: {state['piket_global_counter']}")
        print(f"Используемый прибор: {state['instrument']}")
        print("\nСостояние съемочных станций:")
        if not state["tacheometry_data"]: 
            print("  [Данные съёмки отсутствуют]")
        for st, p_list in state["tacheometry_data"].items():
            st_rom = state["catalog_points"].get(st, {}).get('roman', f"№{st}")
            print(f"  Станция {st_rom} (№{st}): отснято {len(p_list)} пикетов")
            
        print("\nДействия:")
        print("  1 - Начать / Продолжить съёмку на станции")
        print("  2 - Удалить пикет по его глобальному номеру")
        print("  0 - Вернуться в главное меню (или нажмите Enter)")
        
        choice = input("Выбор: ").strip()
        
        if not choice or choice == '0': 
            clear_screen()
            break
        
        elif choice == '1':
            st_idx = input("Введите арабский номер съемочной станции: ").strip()
            if not st_idx:
                continue
                
            if st_idx not in state["catalog_points"]:
                print("Данная точка не найдена в каталоге опорных координат!")
                input("Нажмите Enter...")
                continue
            
            st_h = state["catalog_points"][st_idx]["h"]
            if st_h is None:
                print("Ошибка! У съемочной станции отсутствует уравненная высота H.")
                print("Сначала внесите измерения и уравняйте Высотного Ход (Пункт 2).")
                input("Нажмите Enter...")
                continue
                
            ref_idx = input("Введите номер точки ориентирования лимба прибора: ").strip()
            if not ref_idx:
                continue
                
            if ref_idx == st_idx:
                print("\n[ОШИБКА] Точка ориентирования не может совпадать со станцией стояния прибора!")
                input("Нажмите Enter для повторного ввода...")
                continue
            
            assigned_mo = 0.0
            found_mo = False
            for m in state["measurements"]:
                if (str(m["from"]) == st_idx and str(m["to"]) == ref_idx) or (str(m["from"]) == ref_idx and str(m["to"]) == st_idx):
                    assigned_mo = m["mo"]
                    found_mo = True
                    break
            
            if not found_mo:
                print("МО для данной пары точек не найдено в журналах нивелирования.")
                assigned_mo = parse_angle("Введите значение МО вручную:", state["instrument"])
                if assigned_mo is None: 
                    continue
            else:
                print(f"Автоматически импортировано архивное МО: {decimal_to_dms(assigned_mo)}")
                
            try:
                i_prompt = f"Высота инструмента i (м) [Enter: {last_i}]: " if last_i else "Высота инструмента i (м): "
                i_inp = input(i_prompt).strip()
                if not i_inp and last_i is None:
                    print("[ОШИБКА] Высота инструмента не может быть пустой!")
                    input("Нажмите Enter...")
                    continue
                i_inst = float(i_inp) if i_inp else last_i
                last_i = i_inst
            except ValueError:
                print("Некорректный ввод высоты.")
                input("Нажмите Enter...")
                continue
            
            if st_idx not in state["tacheometry_data"]:
                state["tacheometry_data"][st_idx] = []
                
            print("\nВвод пикетов. Для прекращения съёмки оставьте поле примечания пустым.")
            while True:
                print(f"\n--- Пикет №{state['piket_global_counter']} ---")
                note = input("Описание / Абрис пикета (или Enter для фиксации станции): ").strip()
                if not note: 
                    break
                
                try:
                    d_p_inp = input("Дальномерное расстояние по рейке D' (м): ").strip()
                    if not d_p_inp:
                        print("[ОШИБКА] Расстояние до пикета не может быть пустым!")
                        continue
                    d_prime = float(d_p_inp)
                    
                    beta = parse_angle("Горизонтальный угол (β):", state["instrument"])
                    if beta is None: 
                        continue
                    kl = parse_angle("Вертикальный угол КЛ:", state["instrument"])
                    if kl is None: 
                        continue
                        
                    v_prompt = f"Высота визирования по рейке v (м) [Enter: {last_v}]: " if last_v else "Высота визирования по рейке v (м): "
                    v_v_inp = input(v_prompt).strip()
                    if not v_v_inp and last_v is None:
                        print("[ОШИБКА] Высота визирования не может быть пустой!")
                        continue
                    v_vis = float(v_v_inp) if v_v_inp else last_v
                    last_v = v_vis
                    
                    nu = kl - assigned_mo
                    s_proj = round(d_prime * (math.cos(math.radians(nu)) ** 2), 1)
                    h_prime = round(d_prime * 0.5 * math.sin(2 * math.radians(nu)), 2)
                    h_diff = round(h_prime + i_inst - v_vis, 2)
                    h_piket = round(st_h + h_diff, state["height_digits"])
                    
                    p_data = {
                        "id": state['piket_global_counter'], "note": note, "d_prime": d_prime,
                        "beta": beta, "kl": kl, "nu": nu, "s": s_proj, "h_diff": h_diff, "h_piket": h_piket
                    }
                    
                    state["tacheometry_data"][st_idx].append(p_data)
                    state['piket_global_counter'] += 1
                    save_state()
                    
                    log_and_print(f"   [ОК] Пикет {p_data['id']}: S_заложение={s_proj} м, превышение h={h_diff} м, Высота H={h_piket} м")
                except ValueError:
                    print("Ошибка парсинга чисел. Пикет отклонён. Забейте данные заново.")
            
            st_roman = state["catalog_points"][st_idx]["roman"]
            log_and_print(f"\n=== ТАХЕОМЕТРИЧЕСКИЙ ЖУРНАЛ: СТАНЦИЯ {st_roman} ===")
            print(f"{'№ Пик.':<6} | {'Описание':<12} | {'β (Гориз)':<12} | {'ν (Вертик)':<12} | {'S (м)':<6} | {'h (м)':<6} | {'H (м)':<12}")
            print("-" * 75)
            for p in state["tacheometry_data"][st_idx]:
                print(f"{p['id']:<6} | {p['note']:<12} | {decimal_to_dms(p['beta']):<12} | {decimal_to_dms(p['nu']):<12} | {p['s']:<6.1f} | {p['h_diff']:<6.2f} | {p['h_piket']:<12.2f}")
            input("\nНажмите Enter для продолжения...")

        elif choice == '2':
            if not state["tacheometry_data"]:
                print("Журнал пикетов абсолютно пуст.")
                input("Нажмите Enter...")
                continue
            try:
                p_id_inp = input("Введите сквозной номер пикета для безвозвратного удаления: ").strip()
                if not p_id_inp:
                    continue
                p_id = int(p_id_inp)
                removed = False
                for st, p_list in state["tacheometry_data"].items():
                    for p in p_list:
                        if p["id"] == p_id:
                            p_list.remove(p)
                            removed = True
                            print(f"Пикет №{p_id} успешно удален из архивов съёмки.")
                            save_state()
                            break
                    if removed: 
                        break
                if not removed: 
                    print("Пикет с указанным глобальным индексом не обнаружен.")
            except ValueError:
                print("Неверный формат идентификатора.")
            input("Нажмите Enter...")
            
        else:
            # Несуществующий пункт подменю
            clear_screen()


# =====================================================================
# ИНТЕРФЕЙСНЫЙ БЛОК: СИСТЕМНЫЙ МЕНЕДЖЕР ПРОЕКТОВ
# =====================================================================
def select_project():
    """Управляет созданием, разделением файлов объектов и их динамическим переключением"""
    global CURRENT_PROJECT_FILE, state
    
    while True:
        clear_screen()
        print("\n" + "="*40)
        print("            МЕНЕДЖЕР ПРОЕКТОВ")
        print("="*40)
        
        files = [f for f in os.listdir('.') if f.endswith('.json') and f != 'package.json']
        
        if files:
            print("Обнаруженные существующие объекты:")
            for i, f in enumerate(files, 1):
                proj_name = f.replace('.json', '')
                print(f"  {i} - {proj_name}")
            print("-" * 40)
        else:
            print("[У вас пока нет созданных проектов]")
            
        print("  N - Создать новый проект")
        print("  0 - Выйти из программы")
        print("="*40)
        
        choice = input("Выберите номер объекта или введите 'N': ").strip().lower()
        if not choice:
            continue
        
        if choice == '0':
            print("Завершение сессии. До встречи в полях!")
            exit()
            
        elif choice == 'n':
            name = input("Название нового объекта (без точек и спецсимволов): ").strip()
            if not name:
                print("[ОШИБКА] Название не может быть пустым!")
                input("Нажмите Enter...")
                continue
            CURRENT_PROJECT_FILE = f"{name}.json"
            
            clear_screen()
            print(f"--- Инициализация проекта: {name.upper()} ---")
            instr = input("Введите модель используемого угломерного прибора (теодолита) [стандартно 2Т30]: ").upper().strip() or "2Т30"
            
            state = {
                "coord_digits": 2, 
                "height_digits": 2, 
                "catalog_points": {}, 
                "instrument": instr, 
                "measurements": [], 
                "piket_global_counter": 1, 
                "tacheometry_data": {}
            }
            save_state()
            log_and_print(f"[Успешно] База данных проекта '{name}' сгенерирована.")
            break
            
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(files):
                    CURRENT_PROJECT_FILE = files[idx]
                    load_state() 
                    break
                else:
                    print("Указан несуществующий индекс проекта.")
                    input("Нажмите Enter...")
            except ValueError:
                print("Неизвестная команда меню.")
                input("Нажмите Enter...")


# =====================================================================
# ГЛАВНЫЙ СУПЕР-ХАБ УПРАВЛЕНИЯ (MAIN)
# =====================================================================
def main():
    global state

    clear_screen()
    select_project()
    clear_screen()

    proj_display_name = CURRENT_PROJECT_FILE.replace('.json', '')
    
    while True:
        print("\n" + "="*50)
        print(f"   ГЛАВНОЕ МЕНЮ ТАХЕОМЕТРИИ | ОБЪЕКТ: {proj_display_name.upper()}")
        print("="*50)
        print("1. Каталог опорных точек (Ввод / Просмотр / Изменение)")
        print("2. Высотный ход (Полевой журнал, невязка, уравнивание)")
        print("3. Журнал тахеометрической съемки (Пикеты)")
        print(f"4. Сменить модель теодолита (сейчас: {state['instrument']})")
        print("8. Сменить активный объект / Открыть менеджер проектов")
        print("9. Полностью очистить этот проект (Жёсткий сброс всех таблиц)")
        print("0. Выход из программы")
        print("="*50)
        
        cmd = input("Выберите пункт меню: ").strip()
        
        if not cmd:
            clear_screen()
            continue
            
        if cmd == '0':
            clear_screen()
            log_and_print(f"Сессия работы с объектом '{proj_display_name}' успешно закрыта.")
            break
        elif cmd == '1':
            menu_catalog_points()
        elif cmd == '2':
            menu_height_traverse()
        elif cmd == '3':
            menu_tacheometry()
        elif cmd == '4':
            clear_screen()
            print(f"=== ИЗМЕНЕНИЕ ИНСТРУМЕНТА СЕССИИ ===")
            new_instr = input(f"Введите новую марку прибора (сейчас {state['instrument']}, Enter чтобы оставить): ").upper().strip()
            if new_instr:
                state["instrument"] = new_instr
                save_state()
                print(f"Прибор успешно изменен на {new_instr}.")
            else:
                print("Изменения отменены, сохранен текущий прибор.")
            input("Нажмите Enter для возврата...")
            clear_screen()
        elif cmd == '8':
            select_project()
            proj_display_name = CURRENT_PROJECT_FILE.replace('.json', '')
            clear_screen()
        elif cmd == '9':
            conf = input(f"Вы уверены, что хотите СТЕРЕТЬ все таблицы объекта {proj_display_name}? (да/нет): ").lower().strip()
            if conf == 'да':
                clear_screen()
                instr = input("Введите модель прибора для чистой сессии [стандартно 2Т30]: ").upper().strip() or "2Т30"
                state = {
                    "coord_digits": 2,
                    "height_digits": 2,
                    "catalog_points": {},
                    "instrument": instr,
                    "measurements": [],
                    "piket_global_counter": 1,
                    "tacheometry_data": {}
                }
                save_state()
                print("[СБРОС] Все таблицы проекта очищены. Инициализирована пустая сессия.")
                input("Нажмите Enter...")
            else:
                print("Сброс отменен.")
                input("Нажмите Enter...")
            clear_screen()
        else:
            # Если ввели левое число в ГЛАВНОМ меню — просто чистим экран и выводим меню заново сверху
            clear_screen()

if __name__ == '__main__':
    main()