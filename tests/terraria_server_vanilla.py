#!/usr/bin/env python3
"""
Pytest test suite for Terraria server Docker container.
Tests multi-architecture build and server functionality.
"""

import pytest
import docker
import socket
import time
import subprocess
import json
import platform
from typing import Generator


class TerrariaServerTest:
    """Test helper class for Terraria server operations."""

    def __init__(self):
        self.client = self._get_docker_client()
        self.image_tag = "terraria-server:vanilla-test"
        self.container = None

    def _get_docker_client(self) -> docker.DockerClient:
        """Get Docker client from docker context."""
        try:
            result = subprocess.run(
                ["docker", "context", "inspect"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                context_info = json.loads(result.stdout)
                if context_info and len(context_info) > 0:
                    endpoint = context_info[0].get("Endpoints", {}).get("docker", {}).get("Host", "")
                    if endpoint:
                        return docker.DockerClient(base_url=endpoint)
        except Exception as e:
            raise RuntimeError(f"Could not get Docker context: {e}")

        raise RuntimeError("Could not connect to Docker daemon. Please ensure Docker is running.")

    def build_multi_arch_image(self) -> None:
        """Build the Docker image for all architectures."""
        print("Building multi-arch image for: linux/amd64,linux/arm/v7,linux/arm64,linux/ppc64le")

        cmd = [
            "docker", "buildx", "build",
            "--platform", "linux/amd64,linux/arm/v7,linux/arm64,linux/ppc64le",
            "--load",
            "--tag", self.image_tag,
            "."
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, cwd="../vanilla")
        if result.returncode != 0:
            raise RuntimeError(f"Failed to build multi-arch image: {result.stderr}")

    def start_container(self, platform: str) -> None:
        """Start the Terraria server container for specific platform."""
        self.container = self.client.containers.run(
            self.image_tag,
            platform=platform,
            ports={"7777/tcp": 7777},
            environment={"TEST_MODE": "true"},
            detach=True,
            remove=False
        )
        time.sleep(2)

    def wait_for_server_ready(self, timeout: int = 120, retries: int = 10) -> bool:
        """Wait for the server to be ready by checking logs with retries."""
        for attempt in range(retries):
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    logs = self.container.logs().decode('utf-8')

                    if "Listening on port 7777" in logs:
                        return True

                    if any(error in logs.lower() for error in ["fatal error", "critical", "cannot start"]):
                        break  # Break to retry

                    time.sleep(5)
                except Exception:
                    break  # Break to retry

            if attempt < retries - 1:
                print(f"Attempt {attempt + 1} failed, retrying...")
                time.sleep(10)  # Wait between retries

        return False

    def test_terraria_protocol(self) -> tuple[bool, str]:
        """Test Terraria server protocol by sending a packet."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                sock.connect(("localhost", 7777))

                # Send minimal Terraria packet
                packet = b'\x04\x00\x01\x00'
                sock.send(packet)

                # Receive response
                response = sock.recv(1024).decode('utf-8', errors='ignore')

                return "Multiplayer" in response, response

        except Exception as e:
            return False, str(e)

    def get_logs(self) -> str:
        """Get container logs."""
        if self.container:
            return self.container.logs().decode('utf-8')
        return ""

    def cleanup(self) -> None:
        """Stop and remove the container."""
        if self.container:
            try:
                self.container.stop()
                self.container.remove()
                self.container = None
            except:
                pass


@pytest.fixture(scope="session")
def terraria_test() -> Generator[TerrariaServerTest, None, None]:
    """Pytest fixture that builds the multi-arch image once."""
    print("Starting terraria test fixture - initializing...")
    test = TerrariaServerTest()
    print("Building multi-arch image...")
    test.build_multi_arch_image()
    print("Multi-arch image build complete")
    yield test


def test_multi_arch_build(terraria_test: TerrariaServerTest):
    """Test that the multi-arch Docker image builds successfully."""
    # The fixture already built the image, verify it exists
    try:
        image = terraria_test.client.images.get(terraria_test.image_tag)
        assert image is not None
    except docker.errors.ImageNotFound:
        pytest.fail(f"Multi-arch image {terraria_test.image_tag} was not built successfully")


def should_skip_emulated_on_arm_mac(platform_param: str) -> bool:
    """Check if we should skip emulated platform tests on ARM Mac due to emulation issues."""
    return (platform.machine() in ['arm64', 'aarch64'] and
            platform.system() == 'Darwin' and
            platform_param in ['linux/amd64', 'linux/ppc64le'])

@pytest.mark.parametrize("platform", ["linux/amd64", "linux/arm/v7", "linux/arm64", "linux/ppc64le"])
def test_server_starts_and_listens(terraria_test: TerrariaServerTest, platform: str):
    """Test that the server starts and begins listening on port 7777."""
    if should_skip_emulated_on_arm_mac(platform):
        pytest.skip("Skipping emulated platform test on ARM Mac due to emulation issues")

    try:
        terraria_test.start_container(platform)
        assert terraria_test.wait_for_server_ready(timeout=120, retries=10), \
            f"Server failed to start within timeout. Logs:\n{terraria_test.get_logs()}"
    finally:
        terraria_test.cleanup()


@pytest.mark.parametrize("platform", ["linux/amd64", "linux/arm/v7", "linux/arm64", "linux/ppc64le"])
def test_server_logs_contain_expected_messages(terraria_test: TerrariaServerTest, platform: str):
    """Test that server logs contain expected startup messages."""
    if should_skip_emulated_on_arm_mac(platform):
        pytest.skip("Skipping emulated platform test on ARM Mac due to emulation issues")

    try:
        terraria_test.start_container(platform)
        assert terraria_test.wait_for_server_ready(timeout=120, retries=10)

        logs = terraria_test.get_logs()

        # Check for expected log messages
        expected_messages = [
            "Server binary:",
            "Architecture :",
            "World file:",
            "Listening on port 7777",
            "Terraria Server"
        ]

        missing_messages = []
        for message in expected_messages:
            if message not in logs:
                missing_messages.append(message)

        assert not missing_messages, \
            f"Missing expected log messages: {missing_messages}\nActual logs:\n{logs}"
    finally:
        terraria_test.cleanup()


@pytest.mark.parametrize("platform", ["linux/amd64", "linux/arm/v7", "linux/arm64", "linux/ppc64le"])
def test_terraria_protocol_response(terraria_test: TerrariaServerTest, platform: str):
    """Test that the server responds with valid Terraria protocol."""
    if should_skip_emulated_on_arm_mac(platform):
        pytest.skip("Skipping emulated platform test on ARM Mac due to emulation issues")

    try:
        terraria_test.start_container(platform)
        assert terraria_test.wait_for_server_ready(timeout=120, retries=10)

        # Test protocol multiple times to ensure stability
        success_count = 0
        last_response = ""

        for i in range(5):
            success, response = terraria_test.test_terraria_protocol()
            if success:
                success_count += 1
            last_response = response
            time.sleep(1)

        assert success_count >= 3, \
            f"Protocol test failed too many times. Last response: {last_response}\nLogs:\n{terraria_test.get_logs()}"
    finally:
        terraria_test.cleanup()


if __name__ == "__main__":
    # Run tests when executed directly
    pytest.main([__file__, "-v"])