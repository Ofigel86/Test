#Подключи модуль
import random
past = "gdgd^#$&^$HRJFKFSAFSAFLVhaksvlsahsa+_+_}{}|{}||POPJOWfhohfoehoqhw;fuqw"
len_pass = int(input(""))
aboba = ""

for i in range(len_pass):
    aboba += random.choice(past)
print(aboba)