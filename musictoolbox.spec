# See https://docs.fedoraproject.org/en-US/packaging-guidelines/Python/#_example_spec_file

%define debug_package %{nil}

%define _name musictoolbox

%define mybuildnumber %{?build_number}%{?!build_number:1}

Name:           python-%{_name}
Version:        0.0.75
Release:        %{mybuildnumber}%{?dist}
Summary:        Utilities to help you groom your music collection

License:        GPLv2
URL:            https://github.com/Rudd-O/%{_name}
Source:         %{url}/archive/v%{version}/%{_name}-%{version}.tar.gz

BuildArch:      noarch

%global _description %{expand:
This package contains utilities to curate music collections.}

%description %_description

%package -n python3-%{_name}
Summary:        %{summary}

%description -n python3-%{_name} %_description

%prep
%autosetup -p1 -n %{_name}-%{version}

%generate_buildrequires
%pyproject_buildrequires -t


%build
%pyproject_wheel


%install
%pyproject_install

%pyproject_save_files %{_name}


%check
%tox

%files -n python3-%{_name} -f %{pyproject_files}
%doc README.md


%changelog
* Tue Aug 22 2023 Manuel Amador <rudd-o@rudd-o.com> 0.0.75-1
- First proper RPM packaging release
