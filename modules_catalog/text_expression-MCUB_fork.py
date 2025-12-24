import re
import math
import random
import json
import html
import asyncio
import subprocess
import sys
import os
import tempfile
from datetime import datetime
from pathlib import Path
import base64
import hashlib

def register(kernel):
    user_variables = {}
    data_dir = Path("expr_data")
    data_dir.mkdir(exist_ok=True)
    last_replies = {}

    def save_variables():
        try:
            with open(data_dir / "variables.json", 'w', encoding='utf-8') as f:
                json.dump(user_variables, f, ensure_ascii=False, indent=2)
        except:
            pass

    def load_variables():
        try:
            file_path = data_dir / "variables.json"
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except:
            pass
        return {}

    user_variables = load_variables()

    def clean_text(text):
        if not text:
            return text
        invisible_chars = [
            '\u200b', '\u200c', '\u200d', '\u200e', '\u200f',
            '\u202a', '\u202b', '\u202c', '\u202d', '\u202e',
            '\u2060', '\u2061', '\u2062', '\u2063', '\u2064',
            '\ufeff', '\u00a0', '\u2028', '\u2029', '\u3000',
            '\u3164', '\uffa0',
        ]
        for char in invisible_chars:
            text = text.replace(char, '')
        text = text.replace('󠆜', '').replace('Ꭲ', 'Т').replace('Ꮚ', 'В')
        return text.strip()

    @kernel.register_command('&')
    async def expr_handler(event):
        message_text = event.raw_text[1:]
        last_replies[event.chat_id] = message_text

        if '||' in message_text:
            parts = message_text.split('||', 1)
            code_part = parts[0].strip()
            pipeline_part = parts[1].strip() if len(parts) > 1 else ""
            code_part = clean_text(code_part)
            try:
                result = await execute_pipeline(code_part, pipeline_part, event)
                await event.edit(result[:4000] if len(result) > 4000 else result)
            except Exception as e:
                await event.edit("🧲 Ошибка, смотри логи")
                await kernel.handle_error(e, source="expr_handler", event=event)
            return

        lines = message_text.split('\n')
        processed_lines = []
        for line in lines:
            if '#' in line:
                line = line.split('#')[0].strip()
            if line:
                processed_lines.append(line)
        expr_text = '\n'.join(processed_lines)

        if not expr_text.strip():
            await event.edit("❄️ Пустое выражение")
            return

        try:
            expr_text = clean_text(expr_text)
            expr_text = await substitute_variables(expr_text)
            expr_text = await preprocess_special_functions(expr_text, event)
            result = await process_expression(expr_text)
            if len(result) > 4000:
                result = result[:4000] + "\n... (результат обрезан)"
            await event.edit(result)
        except SyntaxError as e:
            await event.edit("🧲 Ошибка, смотри логи")
            await kernel.handle_error(e, source="expr_handler", event=event)
        except NameError as e:
            await event.edit("🧲 Ошибка, смотри логи")
            await kernel.handle_error(e, source="expr_handler", event=event)
        except Exception as e:
            await event.edit("🧲 Ошибка, смотри логи")
            await kernel.handle_error(e, source="expr_handler", event=event)

    async def execute_pipeline(code, pipeline, event):
        try:
            pipeline = pipeline.strip()
            if pipeline.lower().startswith('bash'):
                cwd = None
                if '"' in pipeline or "'" in pipeline:
                    path_match = re.search(r'["\']([^"\']+)["\']', pipeline)
                    if path_match:
                        cwd = path_match.group(1)
                result = await execute_bash_command(code, cwd)
                return result
            elif pipeline.lower().startswith('python'):
                version = "3"
                if '"' in pipeline or "'" in pipeline:
                    version_match = re.search(r'["\'](\d+(?:\.\d+)?)?["\']', pipeline)
                    if version_match and version_match.group(1):
                        version = version_match.group(1)
                result = await execute_python_code(code, version)
                return result
            else:
                return "❄️ Неизвестный тип конвейера. Используйте: bash или python"
        except Exception as e:
            raise Exception(f"Pipeline error: {str(e)}")

    async def preprocess_special_functions(expr, event):
        expr = clean_text(expr)
        if '@replytext()' in expr:
            reply = await event.get_reply_message()
            if reply and reply.text:
                expr = expr.replace('@replytext()', f'"{clean_text(reply.text)}"')
            else:
                expr = expr.replace('@replytext()', '""')
        bash_pattern = r'@bash\("([^"]+)"(?:,\s*"([^"]+)")?\)'
        for match in re.finditer(bash_pattern, expr):
            try:
                command = match.group(1)
                cwd = match.group(2)
                result = await execute_bash_command(command, cwd)
                expr = expr.replace(match.group(0), f'"{result}"')
            except Exception as e:
                expr = expr.replace(match.group(0), f'"❄️ Bash ошибка: {str(e)}"')
        python_pattern = r'@python\("([^"]+)"\)'
        for match in re.finditer(python_pattern, expr):
            try:
                code = match.group(1)
                result = await execute_python_code(code, "3")
                expr = expr.replace(match.group(0), f'"{result}"')
            except Exception as e:
                expr = expr.replace(match.group(0), f'"❄️ Python ошибка: {str(e)}"')
        python_ver_pattern = r'@python\("([^"]+)",\s*"([^"]+)"\)'
        for match in re.finditer(python_ver_pattern, expr):
            try:
                version = match.group(1)
                code = match.group(2)
                result = await execute_python_code(code, version)
                expr = expr.replace(match.group(0), f'"{result}"')
            except Exception as e:
                expr = expr.replace(match.group(0), f'"❄️ Python ошибка: {str(e)}"')
        funcs = [
            (r'@now\(\)', lambda: datetime.now().isoformat()),
            (r'@now\("([^"]*)"\)', lambda fmt: datetime.now().strftime(fmt)),
            (r'@date\(\)', lambda: datetime.now().strftime("%Y-%m-%d")),
            (r'@date\("([^"]*)"\)', lambda fmt: datetime.now().strftime(fmt)),
            (r'@time\(\)', lambda: datetime.now().strftime("%H:%M:%S")),
            (r'@time\("([^"]*)"\)', lambda fmt: datetime.now().strftime(fmt)),
            (r'@timestamp', lambda: str(int(datetime.now().timestamp()))),
        ]
        for pattern, handler in funcs:
            matches = list(re.finditer(pattern, expr))
            for match in reversed(matches):
                try:
                    if match.groups():
                        result = handler(match.group(1))
                    else:
                        result = handler()
                    expr = expr[:match.start()] + f'"{result}"' + expr[match.end():]
                except:
                    pass
        rand_pattern = r'@rand\((\d+),(\d+)\)'
        for match in re.finditer(rand_pattern, expr):
            try:
                a, b = int(match.group(1)), int(match.group(2))
                expr = expr.replace(match.group(0), str(random.randint(a, b)))
            except:
                pass
        choice_pattern = r'@choice\(([^)]+)\)'
        for match in re.finditer(choice_pattern, expr):
            try:
                args_str = match.group(1)
                items = []
                current = ""
                in_quotes = False
                quote_char = None
                i = 0
                while i < len(args_str):
                    ch = args_str[i]
                    if ch in ('"', "'"):
                        if not in_quotes:
                            in_quotes = True
                            quote_char = ch
                        elif ch == quote_char:
                            in_quotes = False
                            quote_char = None
                        current += ch
                    elif ch == ',' and not in_quotes:
                        item = current.strip().strip('"\'')
                        if item:
                            items.append(item)
                        current = ""
                    else:
                        current += ch
                    i += 1
                if current.strip():
                    items.append(current.strip().strip('"\''))
                if items:
                    selected = random.choice(items)
                    expr = expr.replace(match.group(0), f'"{selected}"')
                else:
                    expr = expr.replace(match.group(0), '""')
            except Exception as e:
                expr = expr.replace(match.group(0), f'"❄️ Ошибка choice: {str(e)}"')
        math_funcs = [
            (r'@sqrt\(([^)]+)\)', lambda x: str(math.sqrt(float(x)))),
            (r'@pow\(([^,]+),([^)]+)\)', lambda x, y: str(math.pow(float(x), float(y)))),
            (r'@sin\(([^)]+)\)', lambda x: str(math.sin(math.radians(float(x))))),
            (r'@cos\(([^)]+)\)', lambda x: str(math.cos(math.radians(float(x))))),
            (r'@tan\(([^)]+)\)', lambda x: str(math.tan(math.radians(float(x))))),
            (r'@abs\(([^)]+)\)', lambda x: str(abs(float(x)))),
            (r'@round\(([^)]+)\)', lambda x: str(round(float(x)))),
            (r'@ceil\(([^)]+)\)', lambda x: str(math.ceil(float(x)))),
            (r'@floor\(([^)]+)\)', lambda x: str(math.floor(float(x)))),
            (r'@len\(([^)]+)\)', lambda x: str(len(x.strip().strip('"\'')))),
            (r'@upper\(([^)]+)\)', lambda x: x.strip().strip('"\'').upper()),
            (r'@lower\(([^)]+)\)', lambda x: x.strip().strip('"\'').lower()),
        ]
        for pattern, handler in math_funcs:
            for match in re.finditer(pattern, expr):
                try:
                    result = handler(*match.groups())
                    expr = expr.replace(match.group(0), f'"{result}"' if isinstance(result, str) and not result.replace('.', '', 1).isdigit() else result)
                except:
                    pass
        hash_funcs = [
            (r'@md5\(([^)]+)\)', lambda x: hashlib.md5(x.strip().strip('"\'').encode()).hexdigest()),
            (r'@sha256\(([^)]+)\)', lambda x: hashlib.sha256(x.strip().strip('"\'').encode()).hexdigest()),
            (r'@base64\(([^)]+)\)', lambda x: base64.b64encode(x.strip().strip('"\'').encode()).decode()),
            (r'@unbase64\(([^)]+)\)', lambda x: base64.b64decode(x.strip().strip('"\'').encode()).decode()),
        ]
        for pattern, handler in hash_funcs:
            for match in re.finditer(pattern, expr):
                try:
                    result = handler(*match.groups())
                    expr = expr.replace(match.group(0), f'"{result}"')
                except:
                    pass
        return expr

    async def execute_bash_command(command, cwd=None):
        try:
            command = command.strip()
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                f.write("#!/bin/bash\n")
                f.write(command)
                temp_file = f.name
            import stat
            os.chmod(temp_file, os.stat(temp_file).st_mode | stat.S_IEXEC)
            process = await asyncio.create_subprocess_shell(
                f'bash {temp_file}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            stdout, stderr = await process.communicate()
            os.unlink(temp_file)
            result_lines = []
            if stdout:
                result_lines.append(stdout.decode().strip())
            if stderr:
                result_lines.append(stderr.decode().strip())
            return '\n'.join(result_lines)[:1000]
        except Exception as e:
            raise Exception(f"Bash error: {str(e)}")

    async def execute_python_code(code, version="3"):
        try:
            code = code.strip()
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, delete_on_close=False) as f:
                f.write(code)
                temp_file = f.name
            if version.startswith('3'):
                python_cmd = sys.executable
            else:
                python_cmd = 'python2'
            process = await asyncio.create_subprocess_exec(
                python_cmd, temp_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            os.unlink(temp_file)
            result_lines = []
            if stdout:
                result_lines.append(stdout.decode().strip())
            if stderr:
                result_lines.append(stderr.decode().strip())
            return '\n'.join(result_lines)[:1000]
        except Exception as e:
            raise Exception(f"Python error: {str(e)}")

    async def substitute_variables(expr):
        var_pattern = r'\$([a-zA-Z_][a-zA-Z0-9_]*)'
        def var_replacer(match):
            var_name = match.group(1)
            if var_name in user_variables:
                value = user_variables[var_name]
                try:
                    float(value)
                    return value
                except ValueError:
                    escaped_value = value.replace('"', '\\"').replace("'", "\\'")
                    return f'"{escaped_value}"'
            return match.group(0)
        return re.sub(var_pattern, var_replacer, expr)

    async def process_expression(expr):
        expr = expr.strip()
        if '|' in expr and not ('||' in expr):
            parts = [p.strip() for p in expr.split('|')]
            current_result = await evaluate_arithmetic(parts[0])
            for pipe_part in parts[1:]:
                current_result = await apply_pipeline_operation(current_result, pipe_part)
            return current_result
        else:
            return await evaluate_arithmetic(expr)

    async def evaluate_arithmetic(expr):
        expr = expr.strip()
        tokens = tokenize_expr(expr)
        for i, token in enumerate(tokens):
            if isinstance(token, str) and token.isdigit():
                tokens[i] = int(token)
        i = 1
        while i < len(tokens):
            if isinstance(tokens[i], str) and tokens[i] in ('*', '/', '//'):
                op = tokens[i]
                if i - 1 < 0 or i + 1 >= len(tokens):
                    raise ValueError("🚨 Недостаточно операндов для оператора")
                left = tokens[i - 1]
                right = tokens[i + 1]
                if not isinstance(left, str):
                    raise ValueError(f"🚨 Левый операнд для {op} должен быть строкой")
                if not isinstance(right, int):
                    raise ValueError(f"🚨 Правый операнд для {op} должен быть числом")
                if op == '*':
                    result = left * right
                elif op == '/':
                    if right <= 0:
                        raise ValueError("🚨 Делитель должен быть положительным")
                    chunk_size = max(1, math.ceil(len(left) / right))
                    result = '\n'.join([left[j:j+chunk_size] for j in range(0, len(left), chunk_size)])
                elif op == '//':
                    if right <= 0:
                        raise ValueError("🚨 Делитель должен быть положительным")
                    chunk_size = max(1, len(left) // right)
                    result = '\n'.join([left[j:j+chunk_size] for j in range(0, len(left), chunk_size)])
                tokens = tokens[:i-1] + [result] + tokens[i+2:]
            else:
                i += 2
        i = 1
        while i < len(tokens):
            if isinstance(tokens[i], str) and tokens[i] in ('+', '-'):
                op = tokens[i]
                if i - 1 < 0 or i + 1 >= len(tokens):
                    raise ValueError("🚨 Недостаточно операндов для оператора")
                left = tokens[i - 1]
                right = tokens[i + 1]
                if not isinstance(left, str) or not isinstance(right, str):
                    raise ValueError(f"🚨 Оба операнда для {op} должны быть строками")
                if op == '+':
                    result = left + right
                elif op == '-':
                    result = left.replace(right, '')
                tokens = tokens[:i-1] + [result] + tokens[i+2:]
            else:
                i += 2
        if len(tokens) != 1:
            raise ValueError("🚨 Некорректное выражение")
        return str(tokens[0]) if isinstance(tokens[0], (int, float)) else tokens[0]

    def tokenize_expr(expr):
        tokens = []
        i = 0
        expr_len = len(expr)
        while i < expr_len:
            char = expr[i]
            if char == '"' or char == "'":
                quote_char = char
                j = i + 1
                while j < expr_len and expr[j] != quote_char:
                    if expr[j] == '\\' and j + 1 < expr_len:
                        j += 1
                    j += 1
                if j < expr_len:
                    string_content = expr[i+1:j]
                    string_content = string_content.replace('\\' + quote_char, quote_char)
                    tokens.append(string_content)
                    i = j + 1
                else:
                    raise SyntaxError("non-closed quotation mark")
            elif char in '0123456789':
                j = i
                while j < expr_len and expr[j] in '0123456789':
                    j += 1
                tokens.append(expr[i:j])
                i = j
            elif char in '+-*/':
                if char == '/' and i + 1 < expr_len and expr[i+1] == '/':
                    tokens.append('//')
                    i += 2
                else:
                    tokens.append(char)
                    i += 1
            elif char.isspace():
                i += 1
            else:
                i += 1
        return tokens

    async def apply_pipeline_operation(text, operation):
        operation = operation.strip()
        if operation.startswith('count'):
            pattern = operation[5:].strip().strip('"\'')
            if not pattern:
                return str(len(text))
            return str(text.count(pattern))
        elif operation == 'trim':
            return text.strip()
        elif operation.startswith('split'):
            delimiter = operation[5:].strip().strip('"\'')
            delimiter = delimiter or ','
            parts = text.split(delimiter)
            return '\n'.join(parts)
        elif operation.startswith('join'):
            delimiter = operation[4:].strip().strip('"\'')
            delimiter = delimiter or ','
            lines = text.split('\n')
            return delimiter.join(lines)
        elif operation == 'unique':
            seen = set()
            result = []
            for char in text:
                if char not in seen:
                    seen.add(char)
                    result.append(char)
            return ''.join(result)
        elif operation == 'sort':
            return ''.join(sorted(text))
        elif operation == 'shuffle':
            chars = list(text)
            random.shuffle(chars)
            return ''.join(chars)
        elif operation == 'reverse':
            return text[::-1]
        elif operation == 'upper':
            return text.upper()
        elif operation == 'lower':
            return text.lower()
        elif operation == 'capitalize':
            return ' '.join(word.capitalize() for word in text.split())
        elif operation == 'title':
            return text.title()
        elif operation.startswith('replace'):
            args = re.findall(r'"([^"]*)"', operation[7:])
            if len(args) >= 2:
                return text.replace(args[0], args[1])
            return text
        elif operation.startswith('grep'):
            pattern = operation[4:].strip().strip('"\'')
            result = []
            for char in text:
                if char in pattern:
                    result.append(char)
            return ''.join(result)
        elif operation.startswith('remove'):
            pattern = operation[6:].strip().strip('"\'')
            result = []
            for char in text:
                if char not in pattern:
                    result.append(char)
            return ''.join(result)
        elif operation.startswith('keeponly'):
            pattern = operation[8:].strip().strip('"\'')
            result = []
            for char in text:
                if char in pattern:
                    result.append(char)
            return ''.join(result)
        elif operation.startswith('repeat'):
            try:
                count = int(operation[6:].strip())
                return text * count
            except:
                return text
        elif operation.startswith('slice'):
            slice_parts = operation[5:].strip().split(':')
            try:
                if len(slice_parts) == 2:
                    start = int(slice_parts[0]) if slice_parts[0] else None
                    end = int(slice_parts[1]) if slice_parts[1] else None
                    return text[start:end]
                elif len(slice_parts) == 1:
                    index = int(slice_parts[0])
                    return text[index]
            except:
                pass
            return text
        elif operation == 'length':
            return str(len(text))
        elif operation == 'words':
            return str(len(text.split()))
        elif operation == 'lines':
            return str(len(text.split('\n')))
        elif operation.startswith('encrypt'):
            try:
                shift = int(operation[7:].strip()) if operation[7:].strip() else 3
                result = []
                for char in text:
                    if char.isalpha():
                        base = ord('a') if char.islower() else ord('A')
                        result.append(chr((ord(char) - base + shift) % 26 + base))
                    else:
                        result.append(char)
                return ''.join(result)
            except:
                return text
        elif operation.startswith('decrypt'):
            try:
                shift = int(operation[7:].strip()) if operation[7:].strip() else 3
                result = []
                for char in text:
                    if char.isalpha():
                        base = ord('a') if char.islower() else ord('A')
                        result.append(chr((ord(char) - base - shift) % 26 + base))
                    else:
                        result.append(char)
                return ''.join(result)
            except:
                return text
        elif operation == 'rot13':
            result = []
            for char in text:
                if 'a' <= char <= 'z':
                    result.append(chr((ord(char) - ord('a') + 13) % 26 + ord('a')))
                elif 'A' <= char <= 'Z':
                    result.append(chr((ord(char) - ord('A') + 13) % 26 + ord('A')))
                else:
                    result.append(char)
            return ''.join(result)
        elif operation.startswith('bash'):
            args = re.findall(r'"([^"]*)"', operation)
            cwd = args[0] if args else None
            return await execute_bash_command(text, cwd)
        elif operation.startswith('python'):
            args = re.findall(r'"([^"]*)"', operation)
            version = args[0] if args else "3"
            return await execute_python_code(text, version)
        elif operation.startswith('zip'):
            other = operation[3:].strip().strip('"\'')
            result = []
            for a, b in zip(text, other):
                result.append(a + b)
            return ''.join(result) + text[len(other):] + other[len(text):]
        elif operation.startswith('chunk'):
            try:
                size = int(operation[5:].strip())
                return '\n'.join(text[i:i+size] for i in range(0, len(text), size))
            except:
                return text
        elif operation.startswith('prefix'):
            prefix = operation[6:].strip().strip('"\'')
            return '\n'.join(prefix + line for line in text.split('\n'))
        elif operation.startswith('suffix'):
            suffix = operation[6:].strip().strip('"\'')
            return '\n'.join(line + suffix for line in text.split('\n'))
        elif operation == 'binary':
            return ' '.join(format(ord(c), '08b') for c in text)
        elif operation == 'hex':
            return ' '.join(hex(ord(c))[2:] for c in text)
        elif operation.startswith('mask'):
            mask_char = operation[4:].strip().strip('"\'') or '*'
            return mask_char * len(text)
        elif operation.startswith('translate'):
            args = operation[9:].strip()
            pairs = re.findall(r'"([^"]*)"\s*:\s*"([^"]*)"', args)
            result = text
            for old, new in pairs:
                result = result.replace(old, new)
            return result
        elif operation.startswith('format'):
            template = operation[6:].strip().strip('"\'')
            return template.replace('{}', text)
        else:
            return text

    @kernel.register_command('exprhelp')
    async def expr_help(event):
        help_text = """
🔮 Advanced String Expression Processor

🧪 Основной синтаксис:
<code>& выражение &</code>

🧬 Конвейеры (||):
<code>&
текст = "привет"
print(текст) || python "3" &</code>

<code>&
ls -la
pwd
whoami || bash &</code>

⚗️ Примеры:
<code>&
word = 500
extion = word - 400
print(extion) || python "3" &</code>

<code>&
echo "Привет"
echo "Мир" || bash &</code>

🔷 Специальные функции:
• <code>@replytext()</code> - текст из ответа
• <code>@bash("ls -la", "/home")</code> - bash с путем
• <code>@python("print('hello')")</code> - выполнить Python
• <code>@choice("A","B","C")</code> - случайный выбор
"""
        await event.edit(help_text, parse_mode='HTML')

    @kernel.register_command('exprauto')
    async def expr_auto(event):
        expr = event.text.split(maxsplit=1)[1] if ' ' in event.text else ''
        if not expr:
            await event.edit("❄️ Использование: .exprauto выражение")
            return
        reply = await event.get_reply_message()
        if not reply or not reply.text:
            await event.edit("❄️ Нужно ответить на сообщение")
            return
        try:
            full_expr = f'& "{reply.text}" {expr} &'
            result = await process_expression(full_expr[2:-2])
            await event.edit(result)
        except Exception as e:
            await event.edit("🧲 Ошибка, смотри логи")
            await kernel.handle_error(e, source="expr_auto", event=event)

    @kernel.register_command('exprset')
    async def expr_set(event):
        args = event.text.split(maxsplit=2)
        if len(args) < 3:
            await event.edit("❄️ Использование: .exprset имя значение")
            return
        var_name = args[1]
        var_value = args[2].strip()
        if (var_value.startswith('"') and var_value.endswith('"')) or \
           (var_value.startswith("'") and var_value.endswith("'")):
            var_value = var_value[1:-1]
        user_variables[var_name] = var_value
        save_variables()
        await event.edit(f"🧿 Переменная <code>{var_name}</code> установлена: <code>{html.escape(var_value)}</code>", parse_mode='HTML')

    @kernel.register_command('exprget')
    async def expr_get(event):
        args = event.text.split()
        if len(args) < 2:
            await event.edit("❄️ Использование: .exprget имя")
            return
        var_name = args[1]
        if var_name in user_variables:
            value = user_variables[var_name]
            await event.edit(f"💠 <code>{var_name}</code> = <code>{html.escape(value)}</code>", parse_mode='HTML')
        else:
            await event.edit(f"❄️ Переменная <code>{var_name}</code> не найдена", parse_mode='HTML')

    @kernel.register_command('exprlist')
    async def expr_list(event):
        if not user_variables:
            await event.edit("📭 Нет сохраненных переменных")
            return
        lines = []
        for name, value in user_variables.items():
            display_value = value[:50] + "..." if len(value) > 50 else value
            lines.append(f"• <code>{name}</code> = <code>{html.escape(display_value)}</code>")
        await event.edit(f"🔭 Переменные ({len(user_variables)}):\n" + "\n".join(lines), parse_mode='HTML')

    @kernel.register_command('exprdel')
    async def expr_del(event):
        args = event.text.split()
        if len(args) < 2:
            await event.edit("❄️ Использование: .exprdel имя")
            return
        var_name = args[1]
        if var_name in user_variables:
            del user_variables[var_name]
            save_variables()
            await event.edit(f"🧿 Переменная <code>{var_name}</code> удалена", parse_mode='HTML')
        else:
            await event.edit(f"❄️ Переменная <code>{var_name}</code> не найдена", parse_mode='HTML')

    @kernel.register_command('exprrand')
    async def expr_rand(event):
        args = event.text.split()
        if len(args) < 2:
            await event.edit("❄️ Использование: .exprrand тип [параметры]")
            return
        data_type = args[1].lower()
        params = ' '.join(args[2:]) if len(args) > 2 else ""
        try:
            if data_type == "int":
                if ',' in params:
                    a, b = map(int, params.split(','))
                    result = str(random.randint(a, b))
                else:
                    result = str(random.randint(0, 100))
            elif data_type == "float":
                if ',' in params:
                    a, b = map(float, params.split(','))
                    result = str(random.uniform(a, b))
                else:
                    result = str(random.random())
            elif data_type == "str":
                length = int(params) if params else 10
                chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                result = ''.join(random.choice(chars) for _ in range(length))
            elif data_type == "hex":
                length = int(params) if params else 8
                result = ''.join(random.choice("0123456789abcdef") for _ in range(length))
            elif data_type == "choice":
                items = [item.strip().strip('"\'') for item in params.split(',')]
                if items:
                    result = random.choice(items)
                else:
                    result = "Нет вариантов"
            elif data_type == "uuid":
                result = ''.join(random.choice("0123456789abcdef") for _ in range(32))
                result = f"{result[:8]}-{result[8:12]}-{result[12:16]}-{result[16:20]}-{result[20:]}"
            elif data_type == "emoji":
                emojis = ["😀","😃","😄","😁","😆","😅","😂","🤣","😊","😇","🙂","🙃","😉","😌","😍","🥰","😘","😗","😙","😚","😋","😛","😝","😜","🤪","🤨","🧐","🤓","😎","🤩","🥳","😏","😒","😞","😔","😟","😕","🙁","☹️","😣","😖","😫","😩","🥺","😢","😭","😤","😠","😡","🤬","🤯","😳","🥵","🥶","😱","😨","😰","😥","😓","🤗","🤔","🤭","🤫","🤥","😶","😐","😑","😬","🙄","😯","😦","😧","😮","😲","🥱","😴","🤤","😪","😵","🤐","🥴","🤢","🤮","🤧","😷","🤒","🤕","🤑","🤠","😈","👿","👹","👺","🤡","💩","👻","💀","☠️","👽","👾","🤖","🎃","😺","😸","😹","😻","😼","😽","🙀","😿","😾"]
                count = int(params) if params else 5
                result = ''.join(random.choice(emojis) for _ in range(count))
            else:
                await event.edit(f"❄️ Неизвестный тип: {data_type}")
                return
            await event.edit(f"🎲 Случайное {data_type}: <code>{result}</code>", parse_mode='HTML')
        except Exception as e:
            await event.edit("🧲 Ошибка, смотри логи")
            await kernel.handle_error(e, source="expr_rand", event=event)

    @kernel.register_command('exprclear')
    async def expr_clear(event):
        user_variables.clear()
        save_variables()
        await event.edit("🧹 Все переменные очищены")

    kernel.cprint(f'{kernel.Colors.GREEN}✅ Загружен модуль: text_expression{kernel.Colors.RESET}')
