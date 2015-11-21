See `diagnose.py` for documentation

# Intended usage
```
curl -L https://raw.githubusercontent.com/vitiral/diagnose/master/diagnose.py > diagnose
sudo ./diagnose
```

# Future development

Long term tests
- cpu+memory burn and temperature monitoring
    - `less /usr/share/doc/cpuburn/README`
        - test memory with `burnMMX`
        - test cpu type with `burn<cputype>`
    - `man lmsensors` to measure cpu temp

