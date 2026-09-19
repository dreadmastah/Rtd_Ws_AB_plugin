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
    ${CMAKE_CURRENT_SOURCE_DIR}/account/include
)

add_executable(astu_execution_sim execution/src/execution_sim_main.cpp)
target_link_libraries(astu_execution_sim PRIVATE astu_core)

if(WIN32)
    add_executable(astu_execution_pipe_host execution/src/execution_pipe_host.cpp)
    target_link_libraries(astu_execution_pipe_host PRIVATE astu_core)

    add_executable(astu_trade_pipe_smoke trade_plugin/src/execution_pipe_client_smoke.cpp)
    target_link_libraries(astu_trade_pipe_smoke PRIVATE astu_core)

    add_executable(
        astu_trade_pipe_live_smoke
        trade_plugin/src/live_execution_pipe_client_smoke.cpp
    )
    target_link_libraries(astu_trade_pipe_live_smoke PRIVATE astu_core)

    add_library(
        astu_trade_amibroker
        SHARED
        trade_plugin/src/astu_trade_plugin.cpp
    )
    target_link_libraries(astu_trade_amibroker PRIVATE astu_core)
    set_target_properties(
        astu_trade_amibroker
        PROPERTIES
        OUTPUT_NAME "AstuTrade"
        PREFIX ""
    )

    add_executable(
        astu_trade_amibroker_exports_smoke
        trade_plugin/src/amibroker_plugin_exports_smoke.cpp
    )
    target_link_libraries(astu_trade_amibroker_exports_smoke PRIVATE astu_core)

    add_executable(
        astu_trade_amibroker_call_smoke
        trade_plugin/src/amibroker_plugin_call_smoke.cpp
    )
    target_link_libraries(astu_trade_amibroker_call_smoke PRIVATE astu_core)
endif()

enable_testing()
add_executable(astu_core_tests tests/core_sim_tests.cpp)
target_link_libraries(astu_core_tests PRIVATE astu_core)
add_test(NAME astu_core_tests COMMAND astu_core_tests)

if(WIN32)
    add_test(
        NAME astu_trade_amibroker_exports
        COMMAND astu_trade_amibroker_exports_smoke $<TARGET_FILE:astu_trade_amibroker>
    )
endif()
