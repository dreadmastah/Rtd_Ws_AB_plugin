#include <filesystem>
#include <fstream>
#include <iostream>
#include <thread>
#include "astu/execution/execution_status.hpp"

using astu::execution::ExecutionStatusPublisher;
ExecutionStatusPublisher publisher(const std::filesystem::path& path) {
    return ExecutionStatusPublisher(path, "TEST", "TEST", "TEST", false, "TEST", "test.jsonl");
}
std::string read(const std::filesystem::path& path) {
    std::ifstream in(path);
    return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}
void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
int main(int argc, char** argv) {
    try {
        if (argc == 3 && std::string(argv[1]) == "--publish") {
            auto status = publisher(argv[2]);
            for (int i = 0; i < 1000; ++i) {
                status.publish();
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            }
            std::cout << "PUBLISH_COUNT=1000\n";
            return 0;
        }
#ifdef _WIN32
        const auto dir = std::filesystem::temp_directory_path() /
            ("astu_status_sharing_" + std::to_string(GetCurrentProcessId()) + "_" +
             std::to_string(GetTickCount64()));
        require(std::filesystem::create_directory(dir), "test directory collision");
        const auto path = dir / "status.json";
        auto status = publisher(path);
        status.publish();
        const auto old = read(path);
        // An ordinary reader denies replacement. A persistent denial must
        // exhaust, preserve old JSON, and remove only this writer's staging.
        {
            std::ifstream held(path);
            require(held.good(), "cannot hold reader");
            const auto begin = std::chrono::steady_clock::now();
            bool failed = false;
            try { status.publish(); }
            catch (const std::exception& exc) {
                failed = std::string(exc.what()).find("attempts=5") != std::string::npos;
            }
            require(failed, "persistent lock did not exhaust clearly");
            require(std::chrono::steady_clock::now() - begin < std::chrono::seconds(2), "unbounded wait");
            require(read(path) == old, "previous snapshot changed on failure");
        }
        // Releasing the reader during bounded retries permits natural recovery.
        std::ifstream held(path);
        std::exception_ptr error;
        std::thread writer([&] { try { status.publish(); } catch (...) { error = std::current_exception(); } });
        std::this_thread::sleep_for(std::chrono::milliseconds(35));
        held.close();
        writer.join();
        if (error) std::rethrow_exception(error);
        // Separate publisher instances overlap; staging cannot be shared.
        std::exception_ptr other_error;
        auto other = publisher(path);
        std::thread second([&] { try { for (int i=0; i<100; ++i) other.publish(); }
                                catch (...) { other_error = std::current_exception(); } });
        try { for (int i=0; i<100; ++i) status.publish(); }
        catch (...) { error = std::current_exception(); }
        second.join();
        if (error) std::rethrow_exception(error);
        if (other_error) std::rethrow_exception(other_error);
        require(read(path).find("ExecutionStatus.v1") != std::string::npos, "invalid final snapshot");
        require(std::distance(std::filesystem::directory_iterator(dir),
                              std::filesystem::directory_iterator{}) == 1, "staging leaked");
        std::filesystem::remove(path);
        std::filesystem::remove(dir);
#endif
        std::cout << "STATUS_SHARING_TESTS=PASS\n";
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << exc.what() << '\n';
        return 1;
    }
}
