#include <sdf/sdf.hh>
#include <sdf/parser.hh>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
int main(int argc, char **argv) {
  if (argc < 3 || argc % 2 == 0) return 10;
  for (int i = 1; i < argc; i += 2) {
    std::ifstream in(argv[i]);
    std::string xml((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    if (!in || xml.empty()) return 11;
    sdf::SDFPtr document(new sdf::SDF());
    if (!sdf::init(document)) return 12;
    sdf::Errors errors;
    if (!sdf::readString(xml, document, errors) || !errors.empty()) {
      for (const auto &error : errors) std::cerr << error.Message() << "\n";
      return 13;
    }
    auto root = document->Root();
    if (!root->HasElement("model")) return 14;
    auto model = root->GetElement("model");
    sdf::ElementPtr selected;
    int matches = 0;
    for (auto plugin = model->GetElement("plugin"); plugin;
         plugin = plugin->GetNextElement("plugin")) {
      if (plugin->Get<std::string>("name") == "turtlebot3_diff_drive") {
        selected = plugin; ++matches;
      }
    }
    if (matches != 1) return 15;
    const bool actual = selected->HasElement("mr3_odometry_period_ns");
    const bool expected = std::string(argv[i+1]) == "true";
    std::cout << "CASE\t" << argv[i] << "\t" << actual << "\t" << expected
              << "\t" << selected->Get<std::string>("mr3_tagged_commands") << "\n";
    if (actual != expected) return 16;
  }
  std::ifstream maps("/proc/self/maps");
  std::string line;
  while (std::getline(maps, line))
    if (line.find("/libsdformat9.so.") != std::string::npos)
      std::cout << "SDK_MAP\t" << line << "\n";
  return 0;
}
