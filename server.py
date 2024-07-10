from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import re

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

def safe_request(url):
    response = requests.get(url)
    try:
        return response.json()
    except ValueError:
        return None

def extract_chinese_name(full_name):
    match = re.search(r'\(([^)]+)\)', full_name)
    if match:
        return match.group(1)
    return full_name

@app.route('/api/company', methods=['GET'])
def get_company_data():
    query = request.args.get('query')
    search_by = request.args.get('search_by', 'name')  # Default search by name

    def fetch_additional_data(business_accounting_no):
        url = f"https://data.gcis.nat.gov.tw/od/data/api/4E5F7653-1B91-4DDC-99D5-468530FAE396?$format=json&$filter=Business_Accounting_NO eq {business_accounting_no}&$skip=0&$top=50"
        return safe_request(url)

    def fetch_capital_stock_amount(business_accounting_no):
        url = f"https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6?$format=json&$filter=Business_Accounting_NO eq {business_accounting_no}&$skip=0&$top=50"
        data = safe_request(url)
        return data[0].get("Capital_Stock_Amount") if data and len(data) > 0 else None

    def fetch_juristic_person_data(juristic_person_name):
        query_encoded = requests.utils.quote(juristic_person_name)
        url = f"https://data.gcis.nat.gov.tw/od/data/api/6BBA2268-1367-4B42-9CCA-BC17499EBE8C?$format=json&$filter=Company_Name like '{query_encoded}' and Company_Status eq 01&$skip=0&$top=50"
        return safe_request(url)

    def process_company_data(company_data, processed_companies, juristic_person_cache, all_companies):
        business_no = company_data["Business_Accounting_NO"]
        if business_no in processed_companies:
            return None

        processed_companies.add(business_no)
        print(f"Processing company: {company_data['Company_Name']}")
        all_companies.append(company_data)

        company_data["additional_data"] = fetch_additional_data(business_no)
        company_data["Capital_Stock_Amount"] = fetch_capital_stock_amount(business_no)

        for person in company_data["additional_data"]:
            juristic_person_name = person.get("Juristic_Person_Name")
            if juristic_person_name:
                if juristic_person_name in juristic_person_cache:
                    juristic_person_company_data = juristic_person_cache[juristic_person_name]
                else:
                    juristic_person_company_data = fetch_juristic_person_data(juristic_person_name)
                    if juristic_person_company_data:
                        juristic_person_cache[juristic_person_name] = juristic_person_company_data
                
                if juristic_person_company_data:
                    for juristic_company in juristic_person_company_data:
                        if juristic_company["Business_Accounting_NO"] not in processed_companies:
                            person["juristic_person_company"] = juristic_company
                            # Recursively process the juristic company
                            process_company_data(juristic_company, processed_companies, juristic_person_cache, all_companies)

        return company_data

    processed_companies = set()
    juristic_person_cache = {}
    all_companies = []

    if search_by == 'responsible_name':
        responsible_name = extract_chinese_name(query)
        url = f"https://data.gcis.nat.gov.tw/od/data/api/4B61A0F1-458C-43F9-93F3-9FD6DA5E1B08?$format=json&$filter=Responsible_Name eq '{responsible_name}'&$skip=0&$top=50"
        companies = safe_request(url)

        if companies:
            companies = [process_company_data(company, processed_companies, juristic_person_cache, all_companies) for company in companies]
            companies = [company for company in companies if company is not None]  # Remove None entries
            return jsonify({
                "mainCompany": companies[0],
                "companies": all_companies,
            })
        return jsonify({"error": "No company found"}), 404

    elif query.isdigit():
        # Search by Business Accounting Number
        url1 = f"https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6?$format=json&$filter=Business_Accounting_NO eq {query}&$skip=0&$top=50"
        company_data = safe_request(url1)
        if not company_data:
            return jsonify({"error": "No company found"}), 404
        company_data = process_company_data(company_data[0], processed_companies, juristic_person_cache, all_companies)

        responsible_name = extract_chinese_name(company_data["Responsible_Name"])
        url2 = f"https://data.gcis.nat.gov.tw/od/data/api/4B61A0F1-458C-43F9-93F3-9FD6DA5E1B08?$format=json&$filter=Responsible_Name eq '{responsible_name}'&$skip=0&$top=50"
        companies_with_same_responsible_name = safe_request(url2)

        if companies_with_same_responsible_name:
            companies_with_same_responsible_name = [process_company_data(company, processed_companies, juristic_person_cache, all_companies) for company in companies_with_same_responsible_name]
            
            # Print company names before filtering out None entries
            print("Companies with the same responsible name before filtering None entries:")
            for company in companies_with_same_responsible_name:
                if company is not None:
                    print(company["Company_Name"])

            companies_with_same_responsible_name = [company for company in companies_with_same_responsible_name if company is not None]  # Remove None entries

            return jsonify({
                "mainCompany": company_data,
                "companies": all_companies,
            })

        return jsonify({"error": "No companies with same responsible name found"}), 404

    else:
        # Search by Company Name
        query_encoded = requests.utils.quote(query)
        url = f"https://data.gcis.nat.gov.tw/od/data/api/6BBA2268-1367-4B42-9CCA-BC17499EBE8C?$format=json&$filter=Company_Name like '{query_encoded}' and Company_Status eq 01&$skip=0&$top=50"
        companies = safe_request(url)
        if companies:
            company_data = process_company_data(companies[0], processed_companies, juristic_person_cache, all_companies)

            responsible_name = extract_chinese_name(company_data["Responsible_Name"])
            url2 = f"https://data.gcis.nat.gov.tw/od/data/api/4B61A0F1-458C-43F9-93F3-9FD6DA5E1B08?$format=json&$filter=Responsible_Name eq '{responsible_name}'&$skip=0&$top=50"
            companies_with_same_responsible_name = safe_request(url2)

            if companies_with_same_responsible_name:
                companies_with_same_responsible_name = [process_company_data(company, processed_companies, juristic_person_cache, all_companies) for company in companies_with_same_responsible_name]
                
                # Print company names before filtering out None entries
                print("Companies with the same responsible name before filtering None entries:")
                for company in companies_with_same_responsible_name:
                    if company is not None:
                        print(company["Company_Name"])

                companies_with_same_responsible_name = [company for company in companies_with_same_responsible_name if company is not None]  # Remove None entries

                return jsonify({
                    "mainCompany": company_data,
                    "companies": all_companies,
                })

        return jsonify({"error": "No company found"}), 404

if __name__ == '__main__':
    app.run(port=5000, debug=True)
