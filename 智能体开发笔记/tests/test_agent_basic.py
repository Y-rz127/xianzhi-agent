import unittest

from AI.examples.base_agent_demo import build_agent
from AI.templates import AgentAction, BaseAgent


class TestBaseAgent(unittest.TestCase):
    def test_memory_and_tools(self):
        agent = BaseAgent()
        agent.remember("k", "v")
        self.assertEqual(agent.recall("k"), "v")

        agent.add_tool("echo", lambda x: x, description="Return input.")
        self.assertEqual(agent.call_tool("echo", 5), 5)

    def test_run_records_trace(self):
        class EchoAgent(BaseAgent):
            def plan(self, user_input: str):
                return [
                    AgentAction("think", "Need echo."),
                    AgentAction("tool", "Call echo tool.", tool_name="echo", tool_args=(user_input,)),
                    AgentAction("respond", "Return observation."),
                ]

        agent = EchoAgent()
        agent.add_tool("echo", lambda x: x, description="Return input.")
        result = agent.run("hello")

        self.assertEqual(result["observations"], ["hello"])
        self.assertEqual(result["trace"][0]["action_type"], "think")
        self.assertEqual(result["memory"]["recent_messages"][0]["role"], "user")

    def test_demo_agent_runs(self):
        agent = build_agent()
        result = agent.run("请介绍 Agent，并计算: 2 + 3")

        self.assertIn("BaseAgent 示例执行完成", result["answer"])
        self.assertIn("5", result["answer"])
        self.assertEqual(result["memory"]["kv"]["last_user_input"], "请介绍 Agent，并计算: 2 + 3")


if __name__ == "__main__":
    unittest.main()

