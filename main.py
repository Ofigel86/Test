import time
meme_dict = {
            "КРИНЖ": "Что-то очень странное или стыдное",
            "ЛОЛ": "Что-то очень смешное",
            "ПОН": "понял, поняла или понятно",
            "ЩИЩ": "одобрение или восторг",
            "КРИПОВЫЙ": "страшный, пугающий",
            "АГРИТСЯ": "злиться",
            "РОФЛ": "шутка"
            }
while True:
    print('Привет😀')
    time.sleep(1)
    word = input("Введите непонятное слово (большими буквами!)🤔: ").upper()
    time.sleep(1)
    if word in list(meme_dict.keys()):
        print("Значение:", meme_dict[word])
    else:
        print("Не найдено😔")
        time.sleep(1)
        q = input('Добавить хочешь?🤨: ').lower()
        if q == 'да':
            add = input("Что хочешь🤔: ")
            add2 = input('Значение🤓: ').lower().capitalize()
            meme_dict[word] = add2
