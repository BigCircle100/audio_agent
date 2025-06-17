import asyncio
import yaml

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from langchain_core.tools import tool
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent

from langchain_openai import ChatOpenAI


class BluetoothAssistant:
    MAX_HISTORY_LENGTH = 10
    SYSTEM_PROMPT = """
        You are a Bluetooth assistant and are responsible for calling the related Bluetooth functions. 
        Please directly answer the user's questions and do not provide any additional output.
        Please determine whether the user's question or request can be answered by your own capabilities or the tools provided. 
        If it cannot be handled, please give the user a direct response.
        When dealing with user questions, please be aware that the user's input may contain typos.
        If the user requests to clear the cache or clear the history of conversations, the model response should only include '__reset_history__' as identifier.
    """

    def __init__(self, config_path="conf.yaml", command='python3', args=['tools.py']):
        self.config_path = config_path
        self.command = command
        self.args = args
        self.conversation_history = [{"role": "system", "content": self.SYSTEM_PROMPT}]

        self.model = None
        self.session = None
        self.agent = None
        self._initialized = False

    def reset_history(self):
        self.conversation_history = [{"role": "system", "content": self.SYSTEM_PROMPT}]

    async def initialize(self):
        # 加载模型配置
        with open(self.config_path, "r") as f:
            config = yaml.safe_load(f)
        self.model = ChatOpenAI(**config)

        # 启动 MCP 子进程及会话
        server_params = StdioServerParameters(command=self.command, args=self.args)
        self._stdio_client_cm = stdio_client(server_params)
        self._stdio_client = await self._stdio_client_cm.__aenter__()

        self.session = await ClientSession(self._stdio_client[0], self._stdio_client[1]).__aenter__()
        await self.session.initialize()

        # 加载工具和创建agent
        self.tools = await load_mcp_tools(self.session)
        self.agent = create_react_agent(self.model, self.tools)

        self._initialized = True

    async def close(self):
        # 关闭会话和子进程
        if self.session:
            await self.session.__aexit__(None, None, None)
        if self._stdio_client_cm:
            await self._stdio_client_cm.__aexit__(None, None, None)
        self._initialized = False

    async def chat(self, user_input: str) -> str:
        if not self._initialized:
            raise RuntimeError("Assistant not initialized. Please call initialize() first.")

        self.conversation_history.append({"role": "user", "content": user_input})

        # 调用agent
        agent_response = await self.agent.ainvoke({"messages": self.conversation_history})
        content = agent_response["messages"][-1].content

        self.conversation_history.append({"role": "assistant", "content": content})

        # 控制对话历史长度，保留system prompt
        if len(self.conversation_history) > self.MAX_HISTORY_LENGTH:
            self.conversation_history = [self.conversation_history[0]] + self.conversation_history[-(self.MAX_HISTORY_LENGTH - 1):]

        return content


async def main():
    assistant = BluetoothAssistant()
    await assistant.initialize()

    print("输入 'exit' 退出对话")

    try:
        while True:
            user_input = input("User: ")
            if user_input.strip().lower() == "exit":
                print("结束对话")
                break

            response = await assistant.chat(user_input)
            print("\nAgent:", response)
            if response.split()[-1] == "__reset_history__":
                assistant.reset_history()
                
    finally:
        await assistant.close()


if __name__ == "__main__":
    asyncio.run(main())
