import json

from utils.database import get_database

from config.config import parser


def is_owner(user_id):
    owners = parser.get("Permission", "Owner")
    for i in json.loads(owners):
        if user_id == i:
            return True
    return False


def is_subowner(author):
    owners = parser.get("Permission", "SubOwner")
    for i in json.loads(owners):
        if author == i:
            return True
    return False


def is_admin(author):
    for i in author.roles:
        if i.permissions.administrator:
            return True
    return False


def is_banned(user_id):
    connect = get_database()
    cur = connect.cursor()
    sql = "select * from BLACKLIST"
    cur.execute(sql)
    banned_list = cur.fetchall()
    connect.close()
    for i in banned_list:
        if i[0] == int(user_id):
            return True
    return False


def check_perm(author):
    if is_owner(author.id):
        return 1
    elif is_subowner(author.id):
        return 2
    elif is_admin(author):
        return 3
    elif is_banned(author.id):
        return 9
    else:
        return 4


def permission(perm):
    def check(ctx):
        return perm >= check_perm(ctx.author)
    return check
