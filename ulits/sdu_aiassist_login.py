import re, hashlib, json, httpx, uuid
from .uniform_login_des import strEnc
from datetime import datetime, timezone


def login(sduid: str, password: str,
          fingerprint: str | None = str(uuid.uuid4())):
    page = httpx.get(
        "https://pass.sdu.edu.cn/cas/login",
        params={
            "service": "https://aiassist.sdu.edu.cn/common/actionCasLogin?redirect_url=https%3A%2F%2Faiassist.sdu.edu.cn%2Fpage%2Fsite%2FnewPc%3Flogin_return%3Dtrue"})
    lt = re.findall(r'"lt" value="(.*?)"', page.text)[0]
    rsa = strEnc(sduid + password + lt, "1", "2", "3")
    execution = re.findall('"execution" value="(.*?)"', page.text)[0]
    event_id = re.findall('"_eventId" value="(.*?)"', page.text)[0]
    murmur_s = hashlib.sha256(fingerprint.encode()).hexdigest()
    device_status = httpx.post(
        "https://pass.sdu.edu.cn/cas/device",
        data={
            "u": strEnc(sduid, "1", "2", "3"),
            "p": strEnc(password, "1", "2", "3"),
            "m": "1",  # mode 1 to get if device registered
            "d": fingerprint, "d_s": murmur_s,
            "d_md5": hashlib.md5(murmur_s.encode()).hexdigest(),  # md5 of d_s
        }, cookies=page.cookies)
    device_status_dict = json.loads(device_status.text)
    match device_status_dict.get("info"):
        case "binded" | "pass":
            pass
        case "bind":
            print("2FA:" + device_status_dict.get("m"))
            tmp = httpx.post(
                "https://pass.sdu.edu.cn/cas/device",
                data={"m": "2"}, cookies=page.cookies)
            if tmp.text == '{"info":"send"}':
                print("SMS verification code sent.")
            else:
                raise SystemError(f"Unknown SMS status: {tmp.text}")
            body = {
                "d": murmur_s, "i": fingerprint, "m": "3", "u": sduid,
                "c": input("Verification Code: "), "s": "1" if input(
                    "Remember this device? (y/N)：") == "y" else "0"}
            k = httpx.post("https://pass.sdu.edu.cn/cas/device",
                           data=body, cookies=page.cookies)
            while k.text == '{"info":"codeErr"}':
                body["c"] = input("Wrong, please retry: ")
                k = httpx.post("https://pass.sdu.edu.cn/cas/device",
                               data=body, cookies=page.cookies)
            if k.text == '{"info":"ok"}':
                print("Login successful.")
                if body["s"] == "1":
                    print(
                        f"For device fingerprint: {fingerprint}, the next login will no longer require a verification code")
        case _:
            print(
                "Please check your username. Device information cannot be loaded by SDU pass.")
            raise SystemError(
                "Unknown device status: {}".format(str(device_status_dict)))
    page = httpx.post(
        "https://pass.sdu.edu.cn/cas/login", cookies=page.cookies, params={
            "service": "https://aiassist.sdu.edu.cn/common/actionCasLogin?redirect_url=https%3A%2F%2Faiassist.sdu.edu.cn%2Fpage%2Fsite%2FnewPc%3Flogin_return%3Dtrue"},
        data={"rsa": rsa, "ul": len(sduid), "pl": len(password), "lt": lt,
              "execution": execution, "_eventId": event_id})
    page = httpx.get(page.headers["location"])
    header = str(page.headers)
    where = header.find("expires=") + 8
    expires = (datetime.strptime(
        header[where:where + 29], "%a, %d-%b-%Y %H:%M:%S GMT")
               .replace(tzinfo=timezone.utc))
    return {
        "cookies": {cookie: value for cookie, value in page.cookies.items()},
        "expires": expires}
