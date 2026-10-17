#include <gazebo/common/Plugin.hh>
#include <dlfcn.h>
#include <iostream>
#include <stdexcept>

int main(int argc, char **argv)
{
  if (argc != 2) {return 2;}
  void *handle = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
  if (!handle) {throw std::runtime_error(dlerror());}
  auto factory = reinterpret_cast<gazebo::ModelPlugin *(*)()>(dlsym(handle, "RegisterPlugin"));
  if (!factory) {throw std::runtime_error(dlerror());}
  for (int i = 0; i < 1000; ++i) {
    gazebo::ModelPlugin *plugin = factory();
    if (!plugin) {return 3;}
    delete plugin;
  }
  if (dlclose(handle) != 0) {throw std::runtime_error(dlerror());}
  std::cout << "PASS: 1000 actual plugin factory/create/destroy cycles; no model Load, callbacks, Gazebo server, world stepping or physical credit\n";
}
