import frappe

def validate(self, method):
    normalize_and_check_duplicates(self)

    # Enqueue the contact update process
    frappe.enqueue(
        update_contacts,
        contacts=self.name,
        phone_nos=self.phone_nos,
        links=self.links,
        queue="long",
        job_name="Update Contacts"
    )

def normalize_and_check_duplicates(doc):
    
    client_no = []
    for row in doc.phone_nos:
        if row.phone:
            phone = row.phone.replace(" ", "")  # Remove spaces from the phone number

            # Normalize phone number by adding country code
            if phone[0] != "+" and phone[0] != "0":
                phone = "+91" + phone
            elif phone[0] == "0":
                phone = "+91" + phone[1:]
            
            row.phone = phone  # Save the cleaned phone back to the document
            client_no.append(phone)

    if not client_no:
        return

    client_no_tuple = tuple(client_no)

    # Duplicate check: Find contacts with the same last 10 digits
    duplicates = []
    for phone in client_no:
        last_10_digits = phone[-10:]  # Get the last 10 digits of the phone number
        duplicate_contacts = frappe.db.sql("""
            SELECT name FROM `tabContact`
            WHERE phone LIKE %(phone_last_10)s AND name != %(contact_name)s
        """, {
            "phone_last_10": "%" + last_10_digits,
            "contact_name": doc.name
        }, as_dict=True)

        if duplicate_contacts:
            duplicates.append({
                "phone": phone,
                "duplicates": [contact['name'] for contact in duplicate_contacts]
            })

    if duplicates:
        error_message = "Duplicate phone numbers found \n"
        for dup in duplicates:
            error_message += f"Phone: {dup['phone']} - Duplicate Contacts: {', '.join(dup['duplicates'])}\n"
        frappe.throw(error_message)

def update_contacts(contacts, phone_nos, links):
    """
    Enqueued function to update contact information in related tables.
    """
    # Collect and normalize the phone numbers
    client_no = []
    for row in phone_nos:
        if row.phone:
            client_no.append(row.phone)

    if not client_no:
        return

    client_no_tuple = tuple(client_no)

    # Determine the highest priority link_doctype
    link_doctype = None
    link_name = None
    for link in links:
        if link.link_doctype == "Customer":
            link_doctype = "Customer"
            link_name = link.link_name
            break
    if not link_doctype:
        for link in links:
            if link.link_doctype == "Lead":
                link_doctype = "Lead"
                link_name = link.link_name
                break
    if not link_doctype and links:
        link_doctype = links[0].link_doctype
        link_name = links[0].link_name
    
    if not links:
        return

    # SQL query to update the Fincall Log
    frappe.db.sql("""
        UPDATE `tabFincall Log`
        SET contact_created = 1
        WHERE customer_no IN %(client_no)s
    """, {"client_no": client_no_tuple})

    # SQL query to update the Employee Fincall
    frappe.db.sql("""
        UPDATE `tabEmployee Fincall`
        SET contact = %(contact_name)s,
            link_to = %(link_to)s,
            link_name = %(link_name)s
        WHERE customer_no IN %(client_no)s
    """, {
        "contact_name": contacts,
        "link_to": link_doctype,
        "link_name": link_name,
        "client_no": client_no_tuple
    })

    # Clear the cache
    frappe.clear_cache()

    # Provide a message indicating completion
    frappe.msgprint("Contacts and links have been updated successfully.")
