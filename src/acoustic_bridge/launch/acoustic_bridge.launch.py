from launch import LaunchDescription
from launch_ros.actions import Node

from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    pkg_share = get_package_share_directory('acoustic_bridge')
    config_file = os.path.join(pkg_share, 'config', 'acoustic_bridge.yaml')

    acoustic_comm_src = os.path.expanduser(
        '~/quadruped_ros2_control/src/acoustic_comm/src'
    )
    existing_pythonpath = os.environ.get('PYTHONPATH', '')
    pythonpath_value = acoustic_comm_src
    if existing_pythonpath:
        pythonpath_value = acoustic_comm_src + os.pathsep + existing_pythonpath

    return LaunchDescription([
        Node(
            package='acoustic_bridge',
            executable='acoustic_bridge_node',
            name='acoustic_bridge',
            output='screen',
            emulate_tty=True,
            parameters=[config_file],
            additional_env={
                'PYTHONPATH': pythonpath_value,
            },
        )
    ])