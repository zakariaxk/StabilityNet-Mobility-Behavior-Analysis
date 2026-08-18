from __future__ import annotations

import unittest
from unittest.mock import patch

from app.config import (
    ANALYSIS_TARGET_FPS,
    ANALYSIS_TARGET_FPS_ENV,
    DETECTION_CONF_THRESHOLD,
    DETECTION_CONF_THRESHOLD_ENV,
    pipeline_config_from_env,
)


class PipelineConfigEnvironmentTests(unittest.TestCase):
    def test_non_finite_target_fps_falls_back_to_default(self) -> None:
        for value in ("nan", "inf", "-inf"):
            with self.subTest(value=value), patch.dict(
                "os.environ",
                {ANALYSIS_TARGET_FPS_ENV: value},
                clear=True,
            ):
                self.assertEqual(
                    pipeline_config_from_env().analysis_target_fps,
                    ANALYSIS_TARGET_FPS,
                )

    def test_non_finite_confidence_threshold_falls_back_to_default(self) -> None:
        for value in ("nan", "inf", "-inf"):
            with self.subTest(value=value), patch.dict(
                "os.environ",
                {DETECTION_CONF_THRESHOLD_ENV: value},
                clear=True,
            ):
                self.assertEqual(
                    pipeline_config_from_env().detector.confidence_threshold,
                    DETECTION_CONF_THRESHOLD,
                )


if __name__ == "__main__":
    unittest.main()
