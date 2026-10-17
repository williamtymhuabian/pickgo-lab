"""PickGo Lab 轻量 MCP stdio 入口。stdout 仅输出 JSON-RPC；不依赖 MCP SDK。"""
import argparse
import json
import sys

import utils
from Constants import APP, MCP


def result_content(value, failed=False):
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, allow_nan=False)}],
            "isError": failed}


def reject_constant(value):
    raise ValueError("Invalid JSON constant: " + value)


def dispatch(context, session, request):
    if (not isinstance(request, dict) or request.get("jsonrpc") != "2.0"
            or not isinstance(request.get("method"), str)
            or ("id" in request and (type(request["id"]) not in (str, int)))):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    method, params = request["method"], request.get("params", {})
    response = {"jsonrpc": "2.0", "id": request.get("id")}
    if "id" not in request:
        if method == "notifications/initialized" and session.get("initialized"):
            session["ready"] = True
        # 无 id 的消息是通知；任何通知都不执行机器人动作。
        return None
    try:
        if not isinstance(params, dict):
            raise ValueError("params must be an object")
        if method == "ping":
            value = {}
        elif method == "initialize":
            if session.get("initialized"):
                raise ValueError("Already initialized")
            if (not isinstance(params.get("protocolVersion"), str)
                    or not isinstance(params.get("capabilities"), dict)
                    or not isinstance(params.get("clientInfo"), dict)):
                raise ValueError("Invalid initialization parameters")
            version = params["protocolVersion"]
            version = version if version in MCP["protocols"] else MCP["protocols"][0]
            value = {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                     "serverInfo": {"name": "pickgo-lab", "title": APP["name"], "version": APP["version"]},
                     "instructions": "Simulation only. grab_and_send returns immediately; poll get_robot_state. "
                                     "Use stop_task to stop motion; protocol cancellation does not stop accepted tasks."}
            session["initialized"] = True
        elif method in ("tools/list", "tools/call"):
            if not session.get("ready"):
                raise ValueError("Initialize and send notifications/initialized first")
            if method == "tools/list":
                if params.get("cursor") is not None:
                    raise ValueError("No pagination cursor is supported")
                value = {"tools": utils.list_tools()}
            else:
                name = params.get("name")
                if not isinstance(name, str) or name not in utils.TOOL:
                    raise ValueError("Unknown tool")
                arguments = params.get("arguments", {})
                utils.validate(arguments, utils.TOOL[name][2])
                try:
                    value = result_content(utils.call_tool(context, name, arguments))
                except (ValueError, RuntimeError, ImportError, OSError) as error:
                    value = result_content({"error": str(error)}, failed=True)
        else:
            response["error"] = {"code": -32601, "message": "Method not found"}
            return response
        response["result"] = value
    except ValueError as error:
        response["error"] = {"code": -32602, "message": str(error)}
    return response


def serve(context):
    session = {}
    while True:
        line = sys.stdin.buffer.readline(MCP["max_message_bytes"] + 1)
        if not line:
            break
        if len(line) > MCP["max_message_bytes"]:
            print("MCP message exceeds 1 MB; closing session", file=sys.stderr)
            break
        try:
            request = json.loads(line.decode("utf-8"), parse_constant=reject_constant)
        except (ValueError, UnicodeError):
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            try:
                reply = dispatch(context, session, request)
            except Exception as error:
                print("MCP error:", type(error).__name__, str(error), file=sys.stderr)
                reply = {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None,
                         "error": {"code": -32603, "message": "Internal error"}}
        if reply is not None:
            sys.stdout.buffer.write((json.dumps(reply, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
            sys.stdout.buffer.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-url", default=f"http://127.0.0.1:{APP['port']}", help="attach to the web service")
    parser.add_argument("--standalone", action="store_true", help="own a separate simulation without the web service")
    args = parser.parse_args()
    context = utils.all_init(None if args.standalone else args.server_url, source="mcp")
    try:
        serve(context)
    finally:
        utils.close(context)


if __name__ == "__main__":
    main()
