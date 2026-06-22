#----------------------------------------------------------------
# Generated CMake target import file for configuration "Release".
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "energyplus::energyplusapi" for configuration "Release"
set_property(TARGET energyplus::energyplusapi APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
set_target_properties(energyplus::energyplusapi PROPERTIES
  IMPORTED_IMPLIB_RELEASE "${_IMPORT_PREFIX}/./energyplusapi.lib"
  IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/./energyplusapi.dll"
  )

list(APPEND _cmake_import_check_targets energyplus::energyplusapi )
list(APPEND _cmake_import_check_files_for_energyplus::energyplusapi "${_IMPORT_PREFIX}/./energyplusapi.lib" "${_IMPORT_PREFIX}/./energyplusapi.dll" )

# Import target "energyplus::energyplus" for configuration "Release"
set_property(TARGET energyplus::energyplus APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
set_target_properties(energyplus::energyplus PROPERTIES
  IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/./energyplus.exe"
  )

list(APPEND _cmake_import_check_targets energyplus::energyplus )
list(APPEND _cmake_import_check_files_for_energyplus::energyplus "${_IMPORT_PREFIX}/./energyplus.exe" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
