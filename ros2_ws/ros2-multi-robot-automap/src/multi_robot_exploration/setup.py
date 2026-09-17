from setuptools import setup

package_name = 'multi_robot_exploration'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='thagasheriff',
    maintainer_email='thagasheriff@e-consystems.com',
    description='Implements frontier-based autonomous exploration for multiple robots.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'battery_manager = multi_robot_exploration.battery_manager:main',
            'control = multi_robot_exploration.control:main',
            'nav2_ready_gate = multi_robot_exploration.nav2_ready_gate:main',
            'robot_status_panel = multi_robot_exploration.status_panel:main',
            'target_detector = multi_robot_exploration.target_detector:main',
            'task_visualizer = multi_robot_exploration.task_visualizer:main',
            'task_evaluator = multi_robot_exploration.task_evaluator:main',
        ],
    },
)
