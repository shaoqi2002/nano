import unittest

from pydantic import ValidationError

from app.schema.job_application import JobApplicationCreate, JobStatusUpdate
from app.service.job_application import infer_job_information


class JobApplicationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
