cmake_minimum_required(VERSION 3.8)
project(multi_robot)


# find dependencies
find_package(ament_cmake REQUIRED)
find_package(gazebo_msgs REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rmw REQUIRED)
find_package(std_msgs REQUIRED)
find_package(gazebo REQUIRED)
find_package(TBB REQUIRED)
find_package(gazebo_ros REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(nlohmann_json REQUIRED)

# Keep embedded provenance correct after either the implementation or pure
# actuator helper changes, including incremental builds.
set(mr3_drive_sources
  ${CMAKE_CURRENT_SOURCE_DIR}/src/mr3_gazebo_diff_drive.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/include/multi_robot/mr3_gazebo_diff_drive.hpp
  ${CMAKE_CURRENT_SOURCE_DIR}/include/multi_robot/paired_wheel_slew.hpp
  ${CMAKE_CURRENT_SOURCE_DIR}/include/multi_robot/mr3_drive_target.hpp)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${mr3_drive_sources})
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/src/mr3_gazebo_diff_drive.cpp mr3_drive_source_sha)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/include/multi_robot/mr3_gazebo_diff_drive.hpp mr3_drive_header_sha)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/include/multi_robot/paired_wheel_slew.hpp mr3_drive_helper_sha)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/include/multi_robot/mr3_drive_target.hpp mr3_drive_target_sha)
add_library(mr3_gazebo_diff_drive SHARED src/mr3_gazebo_diff_drive.cpp)
target_compile_features(mr3_gazebo_diff_drive PUBLIC cxx_std_17)
target_include_directories(mr3_gazebo_diff_drive PRIVATE include ${GAZEBO_INCLUDE_DIRS})
ament_target_dependencies(mr3_gazebo_diff_drive
  gazebo_ros geometry_msgs nav_msgs rclcpp std_msgs tf2 tf2_geometry_msgs tf2_ros)
target_link_libraries(mr3_gazebo_diff_drive ${GAZEBO_LIBRARIES}
  nlohmann_json::nlohmann_json ${CMAKE_DL_LIBS})
target_compile_definitions(mr3_gazebo_diff_drive PRIVATE
  MR3_DRIVE_SOURCE_SHA256="${mr3_drive_source_sha}"
  MR3_DRIVE_HEADER_SHA256="${mr3_drive_header_sha}"
  MR3_DRIVE_HELPER_SHA256="${mr3_drive_helper_sha}"
  MR3_DRIVE_TARGET_SHA256="${mr3_drive_target_sha}")
install(TARGETS mr3_gazebo_diff_drive DESTINATION lib)
install(DIRECTORY vendor/ DESTINATION share/${PROJECT_NAME}/vendor)

# Opt-in diagnostic observer only. No existing driver target/source/flags change.
set(mr3_observer_source ${CMAKE_CURRENT_SOURCE_DIR}/src/mr3_stop_response_observer.cpp)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${mr3_observer_source})
file(SHA256 ${mr3_observer_source} mr3_observer_source_sha)
add_library(mr3_stop_response_observer SHARED src/mr3_stop_response_observer.cpp)
target_compile_features(mr3_stop_response_observer PRIVATE cxx_std_17)
target_include_directories(mr3_stop_response_observer PRIVATE ${GAZEBO_INCLUDE_DIRS})
target_compile_definitions(mr3_stop_response_observer PRIVATE
  MR3_OBSERVER_SOURCE_SHA256="${mr3_observer_source_sha}")
target_link_libraries(mr3_stop_response_observer ${GAZEBO_LIBRARIES}
  nlohmann_json::nlohmann_json ${CMAKE_DL_LIBS})
install(TARGETS mr3_stop_response_observer DESTINATION lib)

add_library(mr3_gazebo_step_plugin SHARED src/mr3_gazebo_step_plugin.cpp)
set_target_properties(mr3_gazebo_step_plugin PROPERTIES OUTPUT_NAME mr3_gazebo_step)
add_executable(mr3_gazebo_step src/mr3_gazebo_step.cpp)
foreach(step_target mr3_gazebo_step_plugin mr3_gazebo_step)
  target_compile_features(${step_target} PUBLIC cxx_std_17)
  target_include_directories(${step_target} PRIVATE include ${GAZEBO_INCLUDE_DIRS})
  target_link_libraries(${step_target} ${GAZEBO_LIBRARIES} TBB::tbb)
endforeach()
install(TARGETS mr3_gazebo_step_plugin DESTINATION lib)
install(TARGETS mr3_gazebo_step DESTINATION lib/${PROJECT_NAME})

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
  ament_add_gtest(test_step_contract test/test_step_contract.cpp)
  target_include_directories(test_step_contract PRIVATE include)
  target_compile_features(test_step_contract PUBLIC cxx_std_17)
  ament_add_gtest(test_paired_wheel_slew test/test_paired_wheel_slew.cpp)
  target_include_directories(test_paired_wheel_slew PRIVATE include)
  target_compile_features(test_paired_wheel_slew PUBLIC cxx_std_17)
  ament_add_gtest(test_drive_target test/test_drive_target.cpp)
  target_include_directories(test_drive_target PRIVATE include)
  target_compile_features(test_drive_target PUBLIC cxx_std_17)
  target_link_libraries(test_drive_target nlohmann_json::nlohmann_json)
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


# Diagnostic-only opt-in SystemPlugin. No change to original driver/step targets.
set(mr3_profile_source ${CMAKE_CURRENT_SOURCE_DIR}/src/mr3_physics_diagnostic_profile.cpp)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${mr3_profile_source})
file(SHA256 ${mr3_profile_source} mr3_profile_source_sha)
add_library(mr3_physics_diagnostic_profile SHARED src/mr3_physics_diagnostic_profile.cpp)
target_compile_features(mr3_physics_diagnostic_profile PUBLIC cxx_std_17)
target_include_directories(mr3_physics_diagnostic_profile PRIVATE ${GAZEBO_INCLUDE_DIRS})
target_link_libraries(mr3_physics_diagnostic_profile ${GAZEBO_LIBRARIES}
  nlohmann_json::nlohmann_json ${CMAKE_DL_LIBS})
target_compile_definitions(mr3_physics_diagnostic_profile PRIVATE
  MR3_PHYSICS_DIAGNOSTIC_SOURCE_SHA256="${mr3_profile_source_sha}")
install(TARGETS mr3_physics_diagnostic_profile DESTINATION lib)

# Opt-in ray provenance SensorPlugin; original targets/sources/flags unchanged.
set(mr3_ray_provenance_source ${CMAKE_CURRENT_SOURCE_DIR}/src/mr3_ray_provenance_observer.cpp)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${mr3_ray_provenance_source})
file(SHA256 ${mr3_ray_provenance_source} mr3_ray_provenance_source_sha)
add_library(mr3_ray_provenance_observer SHARED src/mr3_ray_provenance_observer.cpp)
target_compile_features(mr3_ray_provenance_observer PRIVATE cxx_std_17)
target_include_directories(mr3_ray_provenance_observer PRIVATE ${GAZEBO_INCLUDE_DIRS})
target_link_libraries(mr3_ray_provenance_observer ${GAZEBO_LIBRARIES}
  nlohmann_json::nlohmann_json ${CMAKE_DL_LIBS})
target_compile_definitions(mr3_ray_provenance_observer PRIVATE
  MR3_RAY_PROVENANCE_SOURCE_SHA256="${mr3_ray_provenance_source_sha}")
install(TARGETS mr3_ray_provenance_observer DESTINATION lib)

ament_package()

# MR3 ray/box finite-segment correction (the other collider pairs are unchanged).
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${CMAKE_CURRENT_SOURCE_DIR}/src/mr3_ray_box_corrector.cpp"
  "${CMAKE_CURRENT_SOURCE_DIR}/src/mr3_ray_box_collision.cpp"
  "${CMAKE_CURRENT_SOURCE_DIR}/include/multi_robot/mr3_ray_box_collision.hpp")
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/src/mr3_ray_box_corrector.cpp"
  MR3_RAY_BOX_CORRECTOR_SOURCE_SHA256)
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/src/mr3_ray_box_collision.cpp"
  MR3_RAY_BOX_COLLISION_SOURCE_SHA256)
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/include/multi_robot/mr3_ray_box_collision.hpp"
  MR3_RAY_BOX_COLLISION_HEADER_SHA256)
add_library(mr3_ray_box_corrector SHARED
  src/mr3_ray_box_corrector.cpp src/mr3_ray_box_collision.cpp)
set_target_properties(mr3_ray_box_corrector PROPERTIES CXX_STANDARD 17 CXX_STANDARD_REQUIRED ON)
target_include_directories(mr3_ray_box_corrector PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/include" ${GAZEBO_INCLUDE_DIRS})
target_link_libraries(mr3_ray_box_corrector ${GAZEBO_LIBRARIES} gazebo_ode ${CMAKE_DL_LIBS})
target_compile_definitions(mr3_ray_box_corrector PRIVATE
  MR3_RAY_BOX_CORRECTOR_SOURCE_SHA256="${MR3_RAY_BOX_CORRECTOR_SOURCE_SHA256}"
  MR3_RAY_BOX_COLLISION_SOURCE_SHA256="${MR3_RAY_BOX_COLLISION_SOURCE_SHA256}"
  MR3_RAY_BOX_COLLISION_HEADER_SHA256="${MR3_RAY_BOX_COLLISION_HEADER_SHA256}")
install(TARGETS mr3_ray_box_corrector LIBRARY DESTINATION lib)
install(FILES vendor/mr3_ray_box_corrector/LICENSE-BSD.TXT
  DESTINATION share/${PROJECT_NAME}/vendor/mr3_ray_box_corrector)
