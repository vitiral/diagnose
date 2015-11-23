See `diagnose.py` for documentation

# Intended usage
```
curl -L https://raw.githubusercontent.com/vitiral/diagnose/master/diagnose.py > diagnose && chmod 700 diagnose
sudo ./diagnose
```

# Future development

**diagnose** is now in Beta and is ready for use. However, several of the tests could use expert review and
contribution. In addition, more tests are always welcome. If you have an idea for a test, please open an
issue and I will try to get it included.

For inclusion a test must have these characteristics:
- be relatively easy to implement with simple bash commands (can require a dependency)
- have output that can be analyzed for failure through regexp commands OR a few lines of python

Primarily, I am NOT interested in writing custom diagnostic tools -- this script is intended to **consolodate**
tools, not create them.
