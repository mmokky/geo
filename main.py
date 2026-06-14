import ast
from datetime import datetime
import json
import logging
import math
import os
import re
import sys

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
    """Дублирует важные сообщения и ведомости одновременно в консоль и в файл лога."""
    logger.info(message)

def clear_screen():
    """Очищает экран terminal в зависимости от текущей операционной системы."""
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
    "tacheometry_data": {},
    "traverse_is_calculated": False  # Флаг отслеживания успешного уравнивания хода
}

def save_state():
    """Сохраняет все текущие изменения сессии в выбранный JSON-файл проекта."""
    with open(CURRENT_PROJECT_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=4)

def load_state():
    """Загружает сохраненную структуру данных из выбранного JSON-файла."""
    global state
    if os.path.exists(CURRENT_PROJECT_FILE):
        try:
            with open(CURRENT_PROJECT_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
            if "traverse_is_calculated" not in state:
                state["traverse_is_calculated"] = False
            proj_name = CURRENT_PROJECT_FILE.replace('.json', '')
            log_and_print(f"[ИНФО] Проект '{proj_name}' успешно загружен.")
        except Exception as e:
            log_and_print(f"[ОШИБКА] Не удалось прочитать файл проекта: {e}. Инициализирована пустая сессия.")


# =====================================================================
# МАТЕМАТИЧЕСКИЕ И ВСПОМОГАТЕЛЬНЫЕ ГЕОДЕЗИЧЕСКИЕ ФУНКЦИИ
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
            print("[ОШИБКА] Неверный формат ввода! Схема: Градусы [пробел] Минуты [пробел] Секунды. Повторите.")

def decimal_to_dms(decimal_deg):
    """Конвертирует десятичные градусы в стандартную геодезическую строку ГГ°ММ'СС\"."""
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

def get_station_orientation_angle(st_idx, ref_idx):
    """Вычисляет исходный дирекционный угол направления со станции на точку ориентирования (ОГЗ)."""
    try:
        st_x = state["catalog_points"][str(st_idx)]["x"]
        st_y = state["catalog_points"][str(st_idx)]["y"]
        ref_x = state["catalog_points"][str(ref_idx)]["x"]
        ref_y = state["catalog_points"][str(ref_idx)]["y"]
        
        dx = ref_x - st_x
        dy = ref_y - st_y
        if dx == 0 and dy == 0:
            return 0.0
        alpha = math.degrees(math.atan2(dy, dx))
        return alpha if alpha >= 0 else alpha + 360.0
    except KeyError:
        return 0.0


# =====================================================================
# ИНТЕРФЕЙСНЫЙ БЛОК: КАТАЛОГ ОПОРНЫХ ТОЧЕК
# =====================================================================
def menu_catalog_points():
    """Управление каталогом координат и высот исходных геодезических пунктов."""
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
                x_prompt = f"Координата X (м) [сейчас: {old_data['x']}]: " if 'x' in old_data else "Координата X (м): "
                x_inp = input(x_prompt).strip()
                if not x_inp and 'x' not in old_data:
                    print("[ОШИБКА] Координата X обязательна для новой точки!")
                    input("Нажмите Enter...")
                    continue
                x = round(float(x_inp), state["coord_digits"]) if x_inp else old_data['x']
                
                # Координата Y
                y_prompt = f"Координата Y (м) [сейчас: {old_data['y']}]: " if 'y' in old_data else "Координата Y (м): "
                y_inp = input(y_prompt).strip()
                if not y_inp and 'y' not in old_data:
                    print("[ОШИБКА] Координата Y обязательна для новой точки!")
                    input("Нажмите Enter...")
                    continue
                y = round(float(y_inp), state["coord_digits"]) if y_inp else old_data['y']
                
                # Высота H
                h_old_str = f"{old_data['h']} м" if old_data.get('h') is not None else "неизвестна"
                h_prompt = f"Высота H (м) [сейчас: {h_old_str}]: " if old_data else "Высота H (м) [Enter, если неизвестна]: "
                h_inp = input(h_prompt).strip()
                
                if h_inp:
                    h = round(float(h_inp), state["height_digits"])
                else:
                    h = old_data.get('h') if old_data else None
                
                state["catalog_points"][idx_str] = {"roman": r_num, "x": x, "y": y, "h": h}
                state["traverse_is_calculated"] = False  # Сбрасываем флаг уравнивания при изменении каталога
                save_state()
                log_and_print(f"[УСПЕШНО] Данные точки {r_num} зафиксированы в базе.")
                input("Нажмите Enter для продолжения...")
            except ValueError:
                print("[ОШИБКА] Вводите только числовые значения. Данные отклонены.")
                input("Нажмите Enter...")
                
        elif choice == '2':
            try:
                c_dig = input(f"Округление X, Y в метрах (сейчас {state['coord_digits']}, Enter чтобы оставить): ").strip()
                state["coord_digits"] = int(c_dig) if c_dig else state["coord_digits"]
                
                h_dig = input(f"Округление H в метрах (сейчас {state['height_digits']}, Enter чтобы оставить): ").strip()
                state["height_digits"] = int(h_dig) if h_dig else state["height_digits"]
                
                save_state()
                print("[УСПЕШНО] Параметры округления обновлены.")
            except ValueError:
                print("[ОШИБКА] Некорректный ввод. Параметры оставлены без изменений.")
                input("Нажмите Enter...")
        else:
            clear_screen()


# =====================================================================
# ИНТЕРФЕЙСНЫЙ БЛОК: ВЫСОТНЫЙ ВЕРИФИЦИРОВАННЫЙ ХОД
# =====================================================================
def menu_height_traverse():
    """Журнал геометрического/тригонометрического нивелирования по станциям хода."""
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
        print("  3 - Выполнить расчет невязки и уравнивание высот")
        print("  4 - Показать полную уравненную ведомость хода (только после расчета)")
        print("  0 - Вернуться в главное меню (или нажмите Enter)")
        
        choice = input("Выбор: ").strip()
        
        if not choice or choice == '0':
            clear_screen()
            break
            
        elif choice == '1':
            if len(state["catalog_points"]) < 2:
                print("[ОШИБКА] Для прокладывания хода внесите минимум 2 точки в каталог!")
                input("Нажмите Enter...")
                continue

            clear_screen()    
            print("\n=== ЗАПУЩЕН РЕЖИМ ВВОДА ЖУРНАЛА ===")
            
            while True:
                points_list = [f"{k} ({v['roman']})" for k, v in state['catalog_points'].items()]
                print("(Для выхода из цикла нажмите Enter на запросе точки станции)\n")
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
                        print("[ОШИБКА] Одной из точек нет в каталоге опорной сети! Повторите ввод.")
                        continue
                    
                    old_m = {}
                    for m in state["measurements"]:
                        if m["from"] == f and m["to"] == t:
                            old_m = m
                            break
                    
                    kl = parse_angle("Отсчет по КЛ:", state["instrument"], old_m.get("kl"))
                    if kl is None: 
                        continue
                    kp = parse_angle("Отсчет по КП:", state["instrument"], old_m.get("kp"))
                    if kp is None: 
                        continue
                    
                    d_p_prompt = f"Дальномерное расстояние D' (м) [сейчас: {old_m['d_prime']}]: " if 'd_prime' in old_m else "Дальномерное расстояние D' (м): "
                    d_p_inp = input(d_p_prompt).strip()
                    if not d_p_inp and 'd_prime' not in old_m:
                        print("[ОШИБКА] Расстояние не может быть пустым!")
                        continue
                    d_prime = float(d_p_inp) if d_p_inp else old_m['d_prime']
                    
                    i_prompt = f"Высота оси вращения трубы прибора i (м) [сейчас: {old_m['i']}]: " if 'i' in old_m else "Высота оси вращения трубы прибора i (м): "
                    i_inp = input(i_prompt).strip()
                    if not i_inp and 'i' not in old_m:
                        print("[ОШИБКА] Высота прибора не может быть пустой!")
                        continue
                    inst_h = float(i_inp) if i_inp else old_m['i']
                    
                    v_prompt = f"Высота цели визирования v (м) [сейчас: {old_m['v']}]: " if 'v' in old_m else "Высота цели визирования v (м): "
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
                        log_msg = f"   [ОБНОВЛЕНО] Данные для перегона {state['catalog_points'][str(f)]['roman']} -> {state['catalog_points'][str(t)]['roman']} перезаписаны."
                    else:
                        state["measurements"].append(new_measurement)
                        log_msg = "   [ДОБАВЛЕНО] Новый перегон зафиксирован в базе сессии."
                    
                    state["traverse_is_calculated"] = False  # Сбрасываем флаг уравнивания при добавлении новых данных
                    save_state()
                    
                    f_rom = state["catalog_points"][str(f)]["roman"]
                    t_rom = state["catalog_points"][str(t)]["roman"]
                    print("-" * 60)
                    log_and_print(f"   [Расчет станции] {f_rom} -> {t_rom}:")
                    log_and_print(f"   МО = {decimal_to_dms(mo)} | ν = {decimal_to_dms(nu)} | h' = {h_prime} м | h = {h_diff} м")
                    log_and_print(log_msg)
                    print("-" * 60, "\n")
                    
                except ValueError:
                    print("[ОШИБКА] Ошибка заполнения данных. Измерения текущей станции аннулированы.")
                except KeyError:
                    print("[ОШИБКА] Ошибка сопоставления индексов каталога пунктов.")
            
            # Полевая ведомость по умолчанию при выходе из цикла ввода
            if state["measurements"]:
                log_and_print("\n=== ВЕДОМОСТЬ ПОЛЕВЫХ ИЗМЕРЕНИЙ ВЫСОТНОГО ХОДА ===")
                header = "{:<8} | {:<8} | {:<10} | {:<10} | {:<10} | {:<10} | {:<7} | {:<6} | {:<6} | {:<7} | {:<7}".format('Станция', 'Визир.', 'КЛ', 'КП', 'МО', 'ν (с МО)', "D' (м)", 'i (м)', 'v (м)', "h' (м)", 'h (м)')
                log_and_print(header)
                log_and_print("-" * len(header))
                for m in state["measurements"]:
                    f_rom = state["catalog_points"].get(str(m['from']), {}).get('roman', f"№{m['from']}")
                    t_rom = state["catalog_points"].get(str(m['to']), {}).get('roman', f"№{m['to']}")
                    log_and_print(f"{f_rom:<8} | {t_rom:<8} | {decimal_to_dms(m['kl']):<10} | {decimal_to_dms(m['kp']):<10} | {decimal_to_dms(m['mo']):<10} | {decimal_to_dms(m['nu']):<10} | {m['d_prime']:<7.2f} | {m['i']:<6.2f} | {m['v']:<6.2f} | {m['h_prime']:<7.2f} | {m['h_diff']:<7.2f}")
                input("\nНажмите Enter для продолжения...")
                    
        elif choice == '2':
            if not state["measurements"]:
                print("[ИНФО] Журнал пуст, удалять нечего.")
                input("Нажмите Enter...")
                continue
            try:
                del_inp = input("Введите номер строки для удаления (с 1): ").strip()
                if not del_inp:
                    continue
                idx = int(del_inp) - 1
                if 0 <= idx < len(state["measurements"]):
                    del state["measurements"][idx]
                    state["traverse_is_calculated"] = False
                    save_state()
                    print("[УСПЕШНО] Запись удалена из памяти сессии.")
                else:
                    print("[ОШИБКА] Записи с таким порядковым номером не существует.")
            except ValueError:
                print("[ОШИБКА] Некорректный формат ввода.")
            input("Нажмите Enter...")
                
        elif choice == '3':
            calculate_traverse_results()
            input("\nОбработка хода завершена. Нажмите Enter для возврата...")
            
        elif choice == '4':
            clear_screen()
            if not state.get("traverse_is_calculated", False):
                print("[ЗАБЛОКИРОВАНО] Итоговая ведомость недоступна.")
                print("Сначала необходимо выполнить расчет невязки и уравнивание хода (Пункт 3).")
                input("\nНажмите Enter для возврата...")
            else:
                show_final_traverse_table()
                input("\nПросмотр завершен. Нажмите Enter для возврата...")
        else:
            clear_screen()

def calculate_traverse_results():
    """Вычисляет высотные невязки, сверяет с допуском и распределяет поправки пропорционально длинам плеч."""
    if not state["measurements"]:
        print("[ОШИБКА] В журнале отсутствуют данные для выполнения уравнивания.")
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
        p_eval = ast.literal_eval(pair_str)
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

    if not final_legs:
        log_and_print("[ОШИБКА] Не удалось сформировать плечи хода из журнала измерений.")
        return

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
    
    clear_screen()
    log_and_print("\n=== ВЕДОМОСТЬ ВЫЧИСЛЕНИЯ НЕВЯЗКИ ===")
    log_and_print(f"Полученная невязка fh = {fh:+g} м")
    log_and_print(f"Допустимая невязка fh_доп = ±{abs(fh_dop)} м")
    log_and_print(f"Суммарная протяженность хода S = {sum_s} м")
    
    if abs(fh) > abs(fh_dop):
        log_and_print("[ВНИМАНИЕ] Невязка превышает установленный допуск! Требуется контрольное перенаблюдение.")
    
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
            
    state["traverse_is_calculated"] = True  # Фиксируем статус успешного уравнивания
    save_state()
    
    show_final_traverse_table()

def show_final_traverse_table():
    """Генерирует полную ведомость всех полевых станций высотного хода."""
    if not state["measurements"]:
        print("[ОШИБКА] Нет измерений в базе данных.")
        return

    log_and_print("\n=== ПОЛНАЯ ПОЛЕВАЯ ВЕДОМОСТЬ ВЫСОТНОГО ХОДА ===")
    header = "{:<8} | {:<8} | {:<10} | {:<10} | {:<10} | {:<10} | {:<7} | {:<6} | {:<6} | {:<7} | {:<7}".format('Станция', 'Визир.', 'КЛ', 'КП', 'МО', 'ν (с МО)', "D' (м)", 'i (м)', 'v (м)', "h' (м)", 'h (м)')
    log_and_print(header)
    log_and_print("-" * len(header))
    
    for m in state["measurements"]:
        f_rom = state["catalog_points"].get(str(m['from']), {}).get('roman', f"№{m['from']}")
        t_rom = state["catalog_points"].get(str(m['to']), {}).get('roman', f"№{m['to']}")
        
        log_and_print(
            f"{f_rom:<8} | {t_rom:<8} | "
            f"{decimal_to_dms(m['kl']):<10} | "
            f"{decimal_to_dms(m['kp']):<10} | "
            f"{decimal_to_dms(m['mo']):<10} | "
            f"{decimal_to_dms(m['nu']):<10} | "
            f"{m['d_prime']:<7.2f} | "
            f"{m['i']:<6.2f} | "
            f"{m['v']:<6.2f} | "
            f"{m['h_prime']:<7.2f} | "
            f"{m['h_diff']:<7.2f}"
        )


# =====================================================================
# ИНТЕРФЕЙСНЫЙ БЛОК: ТАХЕОМЕТРИЧЕСКАЯ СЪЕМКА (ПИКЕТЫ)
# =====================================================================
def print_tacheometry_table(st_idx):
    """Генерирует полную ведомость пикетов с автопересчетом дирекционных углов на основе сохраненного ориентира."""
    if not state["tacheometry_data"].get(st_idx):
        log_and_print("[ОШИБКА] Нет данных для вывода таблицы по этой станции.")
        return

    # Автоматически извлекаем ориентир из первого пикета данной станции
    sample_piket = state["tacheometry_data"][st_idx][0]
    ref_idx = sample_piket.get("ref_idx")
    
    if ref_idx:
        alpha_st_ref = get_station_orientation_angle(st_idx, ref_idx)
        ref_roman = state["catalog_points"].get(str(ref_idx), {}).get('roman', f"№{ref_idx}")
        ori_info = f" (Ориентир на точку: {ref_roman})"
    else:
        alpha_st_ref = 0.0
        ori_info = " (Ориентир не задан)"

    st_roman = state["catalog_points"][st_idx]["roman"]
    log_and_print(f"\n=== ТАХЕОМЕТРИЧЕСКИЙ ЖУРНАЛ: СТАНЦИЯ {st_roman}{ori_info} ===")
    
    # Внутренняя функция для жесткого выравнивания без сдвигов из-за UTF-8
    def pad(val, width):
        s = str(val)
        actual_len = len(s)
        if actual_len >= width:
            return s[:width]
        return s + " " * (width - actual_len)

    # Задаем фиксированную ширину столбцов
    w_id = 6
    w_note = 15
    w_d = 7
    w_ang = 11  # Запас под знаки "-", "°", "'", "\""
    w_s = 6
    w_v = 5
    w_h = 7
    w_H = 7
    w_coord = 8

    # Собираем шапку таблицы
    header = (
        f"{pad('№ Пик.', w_id)} | {pad('Описание', w_note)} | {pad('D\' (м)', w_d)} | "
        f"{pad('β (Гориз)', w_ang)} | {pad('КЛ', w_ang)} | {pad('ν (с МО)', w_ang)} | "
        f"{pad('S_зал (м)', w_s)} | {pad('v (м)', w_v)} | {pad('h\' (м)', w_h)} | "
        f"{pad('h (м)', w_h)} | {pad('H (м)', w_H)} | {pad('Дир. угол α', w_ang)} | "
        f"{pad('X (м)', w_coord)} | {pad('Y (м)', w_coord)}"
    )
    log_and_print(header)
    log_and_print("-" * len(header))
    
    # СТРОКА ОРИЕНТИРОВАНИЯ: Выводим её первой перед пикетами
    if ref_idx:
        # Выносим вызов функции из f-строки во внешнюю переменную
        ang_str = decimal_to_dms(0.0)

        ori_row = (
            f"{pad(ref_roman, w_id)} | "
            f"{pad('Ориентир', w_note)} | "
            f"{pad('', w_d)} | "
            f"{pad(ang_str, w_ang)} | "
            f"{pad('', w_ang)} | "
            f"{pad('', w_ang)} | "
            f"{pad('', w_s)} | "
            f"{pad('', w_v)} | "
            f"{pad('', w_h)} | "
            f"{pad('', w_h)} | "
            f"{pad('', w_H)} | "
            f"{pad('', w_ang)} | "
            f"{pad('', w_coord)} | "
            f"{pad('', w_coord)}"
        )
        log_and_print(ori_row)
    
    # СВОДНЫЙ ВЫВОД ПИКЕТОВ
    for p in state["tacheometry_data"][st_idx]:
        alpha_piket = (alpha_st_ref + p['beta']) % 360.0
        p['alpha'] = alpha_piket  
        
        # Предварительное форматирование строк, чтобы избежать вложенных f-строк
        d_str = f"{p['d_prime']:.2f}"
        s_str = f"{p['s']:.2f}"
        v_str = f"{p.get('v', 0.0):.2f}"
        hprime_str = f"{p.get('h_prime', 0.0):.2f}"
        hdiff_str = f"{p['h_diff']:.2f}"
        hpiket_str = f"{p['h_piket']:.{state['height_digits']}f}"
        x_str = f"{p['x']:.{state['coord_digits']}f}"
        y_str = f"{p['y']:.{state['coord_digits']}f}"

        p_row = (
            f"{pad(p['id'], w_id)} | "
            f"{pad(p['note'], w_note)} | "
            f"{pad(d_str, w_d)} | "
            f"{pad(decimal_to_dms(p['beta']), w_ang)} | "
            f"{pad(decimal_to_dms(p['kl']), w_ang)} | "
            f"{pad(decimal_to_dms(p['nu']), w_ang)} | "
            f"{pad(s_str, w_s)} | "
            f"{pad(v_str, w_v)} | "
            f"{pad(hprime_str, w_h)} | "
            f"{pad(hdiff_str, w_h)} | "
            f"{pad(hpiket_str, w_H)} | "
            f"{pad(decimal_to_dms(alpha_piket), w_ang)} | "
            f"{pad(x_str, w_coord)} | "
            f"{pad(y_str, w_coord)}"
        )
        log_and_print(p_row)


def menu_tacheometry():
    """Журнал съёмки пикетов подробностей местности со съемочных станций."""
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
            ref_info = ""
            if p_list:
                r_id = p_list[0].get("ref_idx")
                if r_id:
                    r_rom = state["catalog_points"].get(str(r_id), {}).get('roman', f"№{r_id}")
                    ref_info = f" (ориентир на {r_rom})"
            print(f"  Станция {st_rom} (№{st}){ref_info}: отснято {len(p_list)} пикетов")
            
        print("\nДействия:")
        print("  1 - Начать / Продолжить съёмку на станции")
        print("  2 - Показать все посчитанные пикеты по станции")
        print("  3 - Удалить пикет по его глобальному номеру")
        print("  0 - Вернуться в главное меню (или нажмите Enter)")
        
        choice = input("Выбор: ").strip()
        
        if not choice or choice == '0': 
            clear_screen()
            break
        
        elif choice == '1':
            clear_screen()
            st_idx = input("Введите арабский номер съемочной станции: ").strip()
            if not st_idx: 
                continue
                
            if st_idx not in state["catalog_points"]:
                print("[ОШИБКА] Данная точка не найдена в каталоге опорных координат!")
                input("Нажмите Enter...")
                continue
            
            st_x = state["catalog_points"][st_idx]["x"]
            st_y = state["catalog_points"][st_idx]["y"]
            st_h = state["catalog_points"][st_idx]["h"]
            
            if st_h is None:
                print("[ОШИБКА] У съемочной станции отсутствует уравненная высота H.")
                print("Сначала внесите измерения и уравняйте Высотный Ход (Пункт 2).")
                input("Нажмите Enter...")
                continue
                
            # Если на этой станции уже снимали, берем сохраненный ориентир как подсказку
            suggested_ref = ""
            if st_idx in state["tacheometry_data"] and state["tacheometry_data"][st_idx]:
                suggested_ref = state["tacheometry_data"][st_idx][0].get("ref_idx", "")

            if suggested_ref:
                ref_prompt = f"Введите номер точки ориентирования лимба прибора [прежний: {suggested_ref}]: "
            else:
                ref_prompt = "Введите номер точки ориентирования лимба прибора: "
                
            ref_idx = input(ref_prompt).strip()
            if not ref_idx:
                ref_idx = suggested_ref
            if not ref_idx: 
                continue
                
            if ref_idx == st_idx:
                print("\n[ОШИБКА] Точка ориентирования не может совпадать со станцией стояния прибора!")
                input("Нажмите Enter для повторного ввода...")
                continue

            if ref_idx not in state["catalog_points"]:
                print("[ОШИБКА] Точка ориентирования не найдена в каталоге координат!")
                input("Нажмите Enter...")
                continue

            alpha_st_ref = get_station_orientation_angle(st_idx, ref_idx)
            
            assigned_mo = 0.0
            found_mo = False
            for m in state["measurements"]:
                if str(m["from"]) == st_idx and str(m["to"]) == ref_idx:
                    assigned_mo = m["mo"]
                    found_mo = True
                    break
            
            if not found_mo:
                print("[ИНФО] МО для данной пары точек не найдено в журналах нивелирования.")
                assigned_mo = parse_angle("Введите значение МО вручную:", state["instrument"])
                if assigned_mo is None: 
                    continue
            else:
                print(f"[ИНФО] Автоматически импортировано архивное МО: {decimal_to_dms(assigned_mo)}")
                
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
                print("[ОШИБКА] Некорректный ввод высоты.")
                input("Нажмите Enter...")
                continue
            
            clear_screen()
            
            if st_idx not in state["tacheometry_data"]:
                state["tacheometry_data"][st_idx] = []
                
            print(f"\n=== ЗАПУЩЕНА СЪЕМКА НА СТАНЦИИ {state['catalog_points'][st_idx]['roman']} ===")
            print("Для прекращения съёмки оставьте поле описания пустым.")
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
                    s_proj = round(d_prime * (math.cos(math.radians(nu)) ** 2), 2)
                    h_prime = round(d_prime * 0.5 * math.sin(2 * math.radians(nu)), 2)
                    h_diff = round(h_prime + i_inst - v_vis, 2)
                    h_piket = round(st_h + h_diff, state["height_digits"])
                    
                    alpha_piket = (alpha_st_ref + beta) % 360.0
                    piket_x = round(st_x + s_proj * math.cos(math.radians(alpha_piket)), state["coord_digits"])
                    piket_y = round(st_y + s_proj * math.sin(math.radians(alpha_piket)), state["coord_digits"])
                    
                    p_data = {
                        "id": state['piket_global_counter'], "note": note, "d_prime": d_prime,
                        "beta": beta, "kl": kl, "nu": nu, "s": s_proj, "v": v_vis, "h_diff": h_diff, 
                        "h_prime": h_prime, "h_piket": h_piket, "alpha": alpha_piket, "x": piket_x, "y": piket_y,
                        "ref_idx": ref_idx
                    }
                    
                    state["tacheometry_data"][st_idx].append(p_data)
                    state['piket_global_counter'] += 1
                    save_state()
                    
                    print("-" * 55)
                    log_and_print(f"   [OK] Результаты расчета Пикета №{p_data['id']}:")
                    log_and_print(f"   Координаты:  X = {piket_x:.{state['coord_digits']}f} м | Y = {piket_y:.{state['coord_digits']}f} м")
                    log_and_print(f"   Высота:      H = {h_piket:.{state['height_digits']}f} м")
                    log_and_print(f"   Параметры:   S_зал = {s_proj:.2f} м | h_прев = {h_diff:+.2f} м | α = {decimal_to_dms(alpha_piket)}")
                    print("-" * 55)
                except ValueError:
                    print("[ОШИБКА] Ошибка парсинга чисел. Данные пикета отклонены.")
            
            print_tacheometry_table(st_idx)
            input("\nНажмите Enter для продолжения...")

        elif choice == '2':
            clear_screen()
            if not state["tacheometry_data"]:
                print("[ИНФО] В базе проекта еще нет отснятых пикетов.")
                input("Нажмите Enter...")
                continue
                
            st_idx = input("Введите арабский номер станции для просмотра пикетов: ").strip()
            if not st_idx or st_idx not in state["tacheometry_data"]:
                print("[ОШИБКА] На этой станции съёмка не производилась или она не существует.")
                input("Нажмите Enter...")
                continue
                
            print_tacheometry_table(st_idx)
            input("\nПросмотр завершен. Нажмите Enter...")

        elif choice == '3':
            if not state["tacheometry_data"]:
                print("[ИНФО] Журнал пикетов абсолютно пуст.")
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
                            print(f"[УСПЕШНО] Пикет №{p_id} удален из архивов съёмки.")
                            save_state()
                            break
                    if removed: 
                        break
                if not removed: 
                    print("[ОШИБКА] Пикет с указанным глобальным индексом не обнаружен.")
            except ValueError:
                print("[ОШИБКА] Неверный формат идентификатора.")
            input("Нажмите Enter...")
        else:
            clear_screen()


# =====================================================================
# ИНТЕРФЕЙСНЫЙ БЛОК: СИСТЕМНЫЙ МЕНЕДЖЕР ПРОЕКТОВ
# =====================================================================
def select_project():
    """Управляет созданием, разделением файлов объектов и их динамическим переключением."""
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
            logging.shutdown()
            sys.exit()
            
        elif choice == 'n':
            name = input("Название нового объекта (без точек и спецсимволов): ").strip()
            if not name:
                print("[ОШИБКА] Название не может быть пустым!")
                input("Нажмите Enter...")
                continue
            CURRENT_PROJECT_FILE = f"{name}.json"
            
            clear_screen()
            print(f"--- Инициализация проекта: {name.upper()} ---")
            instr = input("Введите модель используемого прибора (теодолита) [стандартно 2Т30]: ").upper().strip() or "2Т30"
            
            state = {
                "coord_digits": 2, 
                "height_digits": 2, 
                "catalog_points": {}, 
                "instrument": instr, 
                "measurements": [], 
                "piket_global_counter": 1, 
                "tacheometry_data": {},
                "traverse_is_calculated": False
            }
            save_state()
            log_and_print(f"[УСПЕШНО] База данных проекта '{name}' успешно сгенерирована.")
            break
            
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(files):
                    CURRENT_PROJECT_FILE = files[idx]
                    load_state() 
                    break
                else:
                    print("[ОШИБКА] Указан несуществующий индекс проекта.")
                    input("Нажмите Enter...")
            except ValueError:
                print("[ОШИБКА] Неизвестная команда меню.")
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
        print("2. Высотный ход (Полевой журнал, невязка, уравнивание, ведомости)")
        print("3. Журнал тахеометрической съемки (Пикеты + Плановые координаты)")
        print(f"4. Сменить модель теодолита (сейчас: {state['instrument']})")
        print("8. Сменить active объект / Открыть менеджер проектов")
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
            print("=== ИЗМЕНЕНИЕ ИНСТРУМЕНТА СЕССИИ ===")
            new_instr = input(f"Введите новую марку прибора (сейчас {state['instrument']}, Enter чтобы оставить): ").upper().strip()
            if new_instr:
                state["instrument"] = new_instr
                save_state()
                print(f"[УСПЕШНО] Прибор изменен на {new_instr}.")
            else:
                print("[ИНФО] Изменения отменены, сохранен текущий прибор.")
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
                    "tacheometry_data": {},
                    "traverse_is_calculated": False
                }
                save_state()
                print("[СБРОС] Все таблицы проекта очищены. Инициализирована пустая сессия.")
                input("Нажмите Enter...")
            else:
                print("[ИНФО] Сброс отменен.")
                input("Нажмите Enter...")
            clear_screen()
        else:
            clear_screen()

    logging.shutdown()

if __name__ == '__main__':
    main()
