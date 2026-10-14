cmake_minimum_required(VERSION 3.8)
project(multi_robot)


# find dependencies
find_package(ament_cmake REQUIRED)
find_package(gazebo_msgs REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rmw REQUIRED)
find_package(std_msgs REQUIRED)

add_executable(mr3_contact_reducer src/mr3_contact_reducer.cpp)
target_compile_features(mr3_contact_reducer PUBLIC cxx_std_17)
target_include_directories(mr3_contact_reducer PRIVATE include)
ament_target_dependencies(mr3_contact_reducer gazebo_msgs rclcpp rmw std_msgs)
install(TARGETS mr3_contact_reducer DESTINATION lib/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_contact_reducer test/test_contact_reducer.cpp)
  target_include_directories(test_contact_reducer PRIVATE include)
  target_compile_features(test_contact_reducer PUBLIC cxx_std_17)
  ament_target_dependencies(test_contact_reducer gazebo_msgs rmw)
endif()

install(DIRECTORY launch/
  DESTINATION share/${PROJECT_NAME}/launch
)
install(DIRECTORY models/
  DESTINATION share/${PROJECT_NAME}/models
)
install(DIRECTORY rviz/
  DESTINATION share/${PROJECT_NAME}/rviz
)
install(DIRECTORY urdf/
  DESTINATION share/${PROJECT_NAME}/urdf
)
install(DIRECTORY worlds/
  DESTINATION share/${PROJECT_NAME}/worlds
)
install(DIRECTORY params/
  DESTINATION share/${PROJECT_NAME}/params
)

install(DIRECTORY config/
  DESTINATION share/${PROJECT_NAME}/config
)

install(DIRECTORY maps/
  DESTINATION share/${PROJECT_NAME}/maps
)


# ament_environment_hooks("${CMAKE_CURRENT_SOURCE_DIR}/env-hooks/multi_robot.dsv.in")


ament_package()
