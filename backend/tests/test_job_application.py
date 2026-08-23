import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.schema.job_application import JobApplicationCreate, JobStatusUpdate
from app.service.job_application import (
    ExtractedJobInformation,
    infer_job_information,
    infer_job_information_with_agent,
)


class JobApplicationTests(unittest.IsolatedAsyncioTestCase):
    def test_infers_labeled_job_information_and_known_channel(self):
        result = infer_job_information(
            "https://jobs.bytedance.com/campus/position/123",
            "公司：字节跳动，岗位：后端开发，地点：上海；内推",
        )

        self.assertEqual(result["company"], "字节跳动")
        self.assertEqual(result["role"], "后端开发")
        self.assertEqual(result["location"], "上海")
        self.assertEqual(result["channel"], "字节跳动招聘")

    def test_falls_back_to_host_and_path(self):
        result = infer_job_information(
            "https://careers.example.com/jobs/software-engineer", ""
        )

        self.assertEqual(result["company"], "Careers")
        self.assertEqual(result["role"], "software engineer")
        self.assertEqual(result["channel"], "careers.example.com")

    def test_rejects_invalid_urls_and_statuses(self):
        with self.assertRaises(ValidationError):
            JobApplicationCreate(job_url="careers.example.com/jobs/1")
        with self.assertRaises(ValidationError):
            JobStatusUpdate(status="unknown")

    async def test_agent_enrichment_falls_back_without_api_keys(self):
        result = await infer_job_information_with_agent(
            "https://jobs.bytedance.com/campus/position/123",
            "公司：字节跳动，岗位：后端开发，地点：上海",
            None,
            None,
        )

        self.assertEqual(result["company"], "字节跳动")
        self.assertEqual(result["role"], "后端开发")

    async def test_agent_enrichment_uses_extracted_page_content(self):
        class FakeExtractTool:
            async def ainvoke(self, payload):
                self.payload = payload
                return '{"results":[{"content":"招聘：云平台研发工程师，工作地点深圳"}]}'

        class FakeStructuredModel:
            async def ainvoke(self, messages):
                self.messages = messages
                return ExtractedJobInformation(
                    company="示例科技",
                    role="云平台研发工程师",
                    location="深圳",
                    channel="校园招聘官网",
                )

        structured_model = FakeStructuredModel()
        with (
            patch(
                "app.service.job_application.create_web_extract_tool",
                return_value=FakeExtractTool(),
            ),
            patch("app.service.job_application.create_model", return_value=object()),
            patch(
                "app.service.job_application.with_structured_output",
                return_value=structured_model,
            ),
        ):
            result = await infer_job_information_with_agent(
                "https://careers.example.com/jobs/123",
                "校招",
                "sk-test",
                "tvly-test",
            )

        self.assertEqual(result["company"], "示例科技")
        self.assertEqual(result["role"], "云平台研发工程师")
        self.assertEqual(result["location"], "深圳")


if __name__ == "__main__":
    unittest.main()
