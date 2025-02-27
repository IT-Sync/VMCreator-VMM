import requests
import json
import yaml
import time
import tkinter as tk
from tkinter import ttk, messagebox

# Константы API
AUTH_URL = "https://localhost:8000/auth/v4/public/token"
IMAGES_URL = "https://localhost:8000/vm/v3/image"
#API_URL = "https://localhost:8000/vm/v3/"
API_URL = "https://localhost:8000"
EMAIL = "boss@domain.ru"
PASSWORD = "password"

def get_token():
    """Функция получения токена авторизации"""
    auth_data = {"email": EMAIL, "password": PASSWORD}
    headers = {"Content-Type": "application/json"}
    
    try:
        auth_response = requests.post(AUTH_URL, json=auth_data, headers=headers, verify=False)
        auth_response.raise_for_status()
        return auth_response.json().get("token")
    except requests.exceptions.RequestException as e:
        print(f"Ошибка авторизации: {e}")
        return None
def get_images():
    """Функция получения списка образов"""
    token = get_token()
    if not token:
        return []

    cookies = {"x-xsrf-token": token}
    headers = {"X-XSRF-TOKEN": token, "Accept": "application/json"}

    try:
        response = requests.get(f"{API_URL}/vm/v3/image", headers=headers, cookies=cookies, verify=False)
        response.raise_for_status()
        data = response.json()  # Получаем JSON
        print("Ответ API:", json.dumps(data, indent=4, ensure_ascii=False))  # Отладочный вывод

        # Проверяем, что data содержит "list" и это список
        if isinstance(data, dict) and "list" in data and isinstance(data["list"], list):
            return [(image["name"], image["id"], image.get("size_mib", 0)) for image in data["list"]
                    if "name" in image and "id" in image]
        else:
            print("Ошибка: API вернул неожиданные данные.")
            return []
    except requests.exceptions.RequestException as e:
        print(f"Ошибка запроса образов: {e}")
#        return []
# Функция получения доступных VLAN
def get_vlans(retries=5, delay=2):
    """Получение списка доступных VLAN с повторными попытками"""
    token = get_token()
    if not token:
        print("Ошибка: Не удалось получить токен")
        return {}

    headers = {
        "X-XSRF-TOKEN": token,
        "Accept": "application/json"
    }
    cookies = {"x-xsrf-token": token}

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(f"{API_URL}/dsw/v1/cluster/1/dpg", headers=headers, cookies=cookies, verify=False)
            response.raise_for_status()
            data = response.json()
            
            vlan_dict = {vlan["name"]: vlan["id"] for vlan in data.get("list", [])}
            print("Доступные VLAN:", vlan_dict)
            return vlan_dict

        except requests.exceptions.RequestException as e:
            print(f"Ошибка получения VLAN (попытка {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(delay)  # Задержка перед повторной попыткой
            else:
                print("Не удалось получить список VLAN после нескольких попыток")
                return {}


# Функция получения доступных LUN
def get_luns():
    """Получение списка доступных LUN"""
    token = get_token()
    if not token:
        print("Ошибка: Не удалось получить токен")
        return {}

    headers = {
        "X-XSRF-TOKEN": token,
        "Accept": "application/json"
    }
    cookies = {"x-xsrf-token": token}

    try:
        response = requests.get(f"{API_URL}/vm/v3/storage", headers=headers, cookies=cookies, verify=False)
        response.raise_for_status()
        data = response.json()

        #lun_dict = {lun["id"]: (lun["name"], lun["state"]) for lun in data.get("list", [])}
        lun_dict = {lun["name"]: lun["id"] for lun in data.get("list", [])}
        print("Доступные LUN:", lun_dict)
        return lun_dict

    except requests.exceptions.RequestException as e:
        print(f"Ошибка получения LUN: {e}")
        return {}


# Функция для загрузки серверов из YAML-файла
def load_servers(file_path="servers.yaml"):
    try:
        with open(file_path, "r") as file:
            data = yaml.safe_load(file)
            return data.get("servers", [])
    except Exception as e:
        print(f"Ошибка загрузки сервера: {e}")
        return []
#
def create_vm():
    """Создание ВМ на основе списка серверов"""
    token = get_token()
    if not token:
        messagebox.showerror("Ошибка", "Не удалось получить токен авторизации")
        return

    selected_image = image_var.get()
    selected_cpu = cpu_var.get()
    selected_ram = ram_var.get()
    image_id = image_dict.get(selected_image)
    ram_mib = int(selected_ram) * 1024  # Перевод в MiB

    if not (selected_image and selected_cpu and selected_ram):
        messagebox.showerror("Ошибка", "Выберите параметры ВМ")
        return

    servers = load_servers()
    vlans = get_vlans()
    luns = get_luns()
    
    headers = {
        "X-XSRF-TOKEN": token,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    cookies = {"x-xsrf-token": token}

    for server in servers:
        vlan_id = vlans.get(server["bridge"])
        lun_id = luns.get(server["lun"])
        if vlan_id is None:
            print(f"Ошибка: VLAN {server['bridge']} не найден")
            continue
        
        if lun_id is None:
            print(f"Ошибка: LUN {server['lun']} не найден")
            continue

        payload = {
            "account": 100000,
            "cluster": 1,
            "cpu_number": int(selected_cpu),
            "ram_mib": ram_mib,
            #"hdd_mib": 30720,
            "hdd_mib": selected_image_size.get(), 
            "snapshot_ram": True,
            "snapshots_allowed": True,
            "image": image_id,
            "hot_plug": True,
            "live_resize": True,
            "storage": lun_id,
            "custom_interfaces": [  # Указание VLAN
                {
                    "model": "virtio",
                    "is_main_network": True,
                    "dpg_id": vlan_id,
                    "no_ip": True
                }
            ],
            "recipe_list": [
                {
                    "recipe": 2,
                    "recipe_params": [
                        {"name": "address", "value": server["address"]},
                        {"name": "netmask", "value": server["netmask"]},
                        {"name": "gateway", "value": server["gateway"]},
                        {"name": "dns_server", "value": server["dns_server"]}
                    ]
                },
                {"recipe": 1, "send_email": False, "recipients": []}
            ],
            "name": f"vm_{server['server_name']}"
        }

        try:
            response = requests.post(f"{API_URL}/vm/v3/host", json=payload, headers=headers, cookies=cookies, verify=False)
            response.raise_for_status()
            print(f"ВМ {server['server_name']} успешно создана: {response.json()}")
        except requests.exceptions.RequestException as e:
            print(f"Ошибка создания ВМ {server['server_name']}: {e}")


servers = load_servers()

# Создание GUI
root = tk.Tk()
root.title("Создание ВМ")

notebook = ttk.Notebook(root)
tab1 = ttk.Frame(notebook)
notebook.add(tab1, text="Настройки ВМ")
notebook.pack(expand=True, fill="both")

# Получаем список [(name, id, size_mib)]
images = get_images()

# Создаём отображаемый список с форматированием: "ID :: name :: size_mib"
image_names = [f"{img_id} :: {name} :: {size_mib} MB" for name, img_id, size_mib in images]

# Связка formatted_name -> id
image_dict = {f"{img_id} :: {name} :: {size_mib} MB": img_id for name, img_id, size_mib in images}

# Выпадающий список
image_var = tk.StringVar()
image_dropdown = ttk.Combobox(tab1, textvariable=image_var, values=image_names, state="readonly")
image_dropdown.pack(fill="x", padx=10)

# Добавим переменную для хранения размера диска
selected_image_size = tk.IntVar(value=30720)  # Значение по умолчанию

def on_image_selected(event):
    selected_info = image_var.get()
    selected_id = image_dict.get(selected_info)
    
    # Найти соответствующий размер образа
    for name, img_id, size_mib in images:
        if img_id == selected_id:
            selected_image_size.set(size_mib)  # Обновляем размер HDD
            break

    print(f"Выбран образ: {selected_info}, ID: {selected_id}, Размер диска: {selected_image_size.get()} MB")

image_dropdown.bind("<<ComboboxSelected>>", on_image_selected)

# Поля для CPU и RAM
ttk.Label(tab1, text="Количество CPU:").pack(pady=5, anchor="w")
cpu_var = tk.IntVar(value=1)
cpu_spinbox = ttk.Spinbox(tab1, from_=1, to=16, textvariable=cpu_var)
cpu_spinbox.pack(fill="x", padx=10)

ttk.Label(tab1, text="Объем RAM (ГБ):").pack(pady=5, anchor="w")
ram_var = tk.IntVar(value=1)
ram_spinbox = ttk.Spinbox(tab1, from_=1, to=64, textvariable=ram_var)
ram_spinbox.pack(fill="x", padx=10)


# Создаём таблицу
columns = ("server_name", "address", "netmask", "gateway", "dns_server", "bridge","lun")
tree = ttk.Treeview(tab1, columns=columns, show="headings")

# Заголовки колонок
for col in columns:
    tree.heading(col, text=col)
    tree.column(col, width=120)

# Заполняем таблицу серверами
for server in servers:
    tree.insert("", "end", values=(
        server["server_name"],
        server["address"],
        server["netmask"],
        server["gateway"],
        server["dns_server"],
        server["bridge"],
        server["lun"],
    ))

# Добавляем скроллбар
scrollbar = ttk.Scrollbar(tab1, orient="vertical", command=tree.yview)
tree.configure(yscroll=scrollbar.set)

tree.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")




# Кнопка "Создать VM"
create_button = ttk.Button(tab1, text="Создать VM", command=create_vm)
create_button.pack(pady=10)

# Запуск GUI
root.mainloop()
