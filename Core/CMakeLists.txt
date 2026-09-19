cmake_minimum_required(VERSION 3.20)
project(AstuCoreScaffold LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(astu_core INTERFACE)
target_include_directories(astu_core INTERFACE
    ${CMAKE_CURRENT_SOURCE_DIR}/common/include
    ${CMAKE_CURRENT_SOURCE_DIR}/trade_plugin/include
    ${CMAKE_CURRENT_SOURCE_DIR}/execution/include
    ${CMAKE_CURRENT_SOURCE_DIR}/wsrtd/include
    ${CMAKE_CURRENT_SOURCE_DIR}/ipc/include
)

add_executable(astu_execution_sim execution/src/execution_sim_main.cpp)
target_link_libraries(astu_execution_sim PRIVATE astu_core)

enable_testing()
add_executable(astu_core_tests tests/core_sim_tests.cpp)
target_link_libraries(astu_core_tests PRIVATE astu_core)
add_test(NAME astu_core_tests COMMAND astu_core_tests)
